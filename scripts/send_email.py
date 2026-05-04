import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


def _attach_csv(msg, csv_path):
    p = Path(csv_path)
    if not p.exists():
        logger.warning(f'CSV attachment not found: {csv_path}')
        return
    with open(p, 'rb') as f:
        part = MIMEBase('text', 'csv')
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{p.name}"')
    msg.attach(part)


def send_daily_email(to_email, from_email, password, html_content,
                     attachment_path, date_str, predictions, subject_override=None):
    """Send MLB report email with CSV attachments (slate + value_bets)."""
    all_bets = [b for g in predictions for b in g.get('predictions', {}).get('value_bets', [])]
    high_conf = [b for b in all_bets if b.get('confidence') == 'HIGH']

    subject = subject_override or (
        f"\u26be MLB Report {date_str} \u2014 {len(predictions)} Games | "
        f"{len(all_bets)} Value Bets ({len(high_conf)} HIGH)"
    )

    plain_lines = [
        f"MLB Daily Report \u2014 {date_str}", "",
        f"Games: {len(predictions)}",
        f"Value bets: {len(all_bets)}",
        f"HIGH confidence: {len(high_conf)}", "",
        "=== MODEL PICKS ==="
    ]
    for b in sorted(all_bets, key=lambda x: x.get('edge_pct', 0), reverse=True):
        pfx = '+' if b['odds'] > 0 else ''
        plain_lines.append(
            f"[{b['confidence']}] {b['pick']} @ {pfx}{b['odds']} "
            f"| Edge +{b['edge_pct']}% | Kelly {b['kelly_pct']}%"
        )
    plain_lines += ["", "Full details in attached CSV files.", "", "Gamble responsibly."]

    msg = MIMEMultipart('mixed')
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('\n'.join(plain_lines), 'plain'))
    alt.attach(MIMEText(html_content, 'html'))
    msg.attach(alt)

    # Attach individual CSVs instead of ZIP
    base = Path(attachment_path).parent
    for csv_name in ['slate.csv', 'value_bets.csv', 'lineups.csv', 'weather.csv',
                     'odds.csv', 'monte_carlo.csv', 'model_reasoning.csv']:
        _attach_csv(msg, base / csv_name)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        logger.info(f'Email sent \u2192 {to_email}')


def send_results_email(to_email, from_email, password, html_content,
                       csv_path, date_str, subject_override=None):
    """Send post-game results email with results CSV attached."""
    subject = subject_override or f"\ud83d\udccb MLB Results {date_str} \u2014 Model Pick Scorecard"

    msg = MIMEMultipart('mixed')
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('See attached CSV for full model pick results.', 'plain'))
    alt.attach(MIMEText(html_content, 'html'))
    msg.attach(alt)

    _attach_csv(msg, csv_path)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        logger.info(f'Results email sent \u2192 {to_email}')
