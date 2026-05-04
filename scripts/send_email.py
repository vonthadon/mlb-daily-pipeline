import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


def send_daily_email(to_email, from_email, password, html_content, attachment_path,
                     date_str, predictions, subject_override=None):
    """Send MLB report email via Gmail SMTP with HTML body and ZIP attachment."""
    all_bets = [b for g in predictions for b in g.get('predictions', {}).get('value_bets', [])]
    high_conf = [b for b in all_bets if b.get('confidence') == 'HIGH']

    subject = subject_override or (
        f"⚾ MLB Report {date_str} — {len(predictions)} Games | "
        f"{len(all_bets)} Value Bets ({len(high_conf)} HIGH)"
    )

    # Plain-text fallback
    plain_lines = [f"MLB Daily Report — {date_str}", "",
                   f"Games: {len(predictions)}", f"Value bets: {len(all_bets)}",
                   f"HIGH confidence: {len(high_conf)}", "", "=== MODEL PICKS ==="]
    for b in sorted(all_bets, key=lambda x: x.get('edge_pct', 0), reverse=True):
        pfx = '+' if b['odds'] > 0 else ''
        plain_lines.append(f"[{b['confidence']}] {b['pick']} @ {pfx}{b['odds']} | Edge +{b['edge_pct']}% | Kelly {b['kelly_pct']}%")
    plain_lines += ["", "Full details in attached ZIP.", "", "Gamble responsibly."]

    msg = MIMEMultipart('mixed')
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('\n'.join(plain_lines), 'plain'))
    alt.attach(MIMEText(html_content, 'html'))
    msg.attach(alt)

    zip_path = Path(attachment_path)
    if zip_path.exists():
        with open(zip_path, 'rb') as f:
            part = MIMEBase('application', 'zip')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{zip_path.name}"')
        msg.attach(part)
    else:
        logger.warning(f'Attachment not found: {attachment_path}')

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        logger.info(f'Email sent → {to_email}')
