// Builds the Supabase Auth email templates in this folder from one layout.
//
//   node supabase/templates/build.mjs
//
// Edit the wording here, not in the .html files, then rebuild. The layout
// matches the campground alert emails (backend/app/alert_emails.py): Trekly
// wordmark, cream background, a white card with a heading, one short
// paragraph and one button, a fallback link, and a short footer.
//
// Every link goes through our own site ({{ .SiteURL }}/auth/confirm), never
// {{ .ConfirmationURL }} (which points at supabase.co). Subjects live in
// supabase/config.toml for local and are pasted into the dashboard for hosted.
// The files are Go templates: {{ ... }} is filled in by Supabase Auth.

import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const INK = "#283618";
const MUTED = "#5b6450";
const CREAM = "#fefae0";
const OLIVE = "#606c38";
const BUTTON = "#a25d20"; // the site's rust fill; white text on it passes 4.5:1
const BORDER = "#e3e0c8";
const SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
const SERIF = "Georgia,'Times New Roman',serif";
const SUPPORT = "treklyusersupport@gmail.com";

const confirmUrl = (type) => `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=${type}`;

export const TEMPLATES = [
  {
    file: "confirmation.html",
    subject: "Confirm your Trekly account",
    preheader: "One click to confirm your email and finish setting up Trekly.",
    heading: "Confirm your email",
    body: "Thanks for signing up for Trekly. Confirm this is your email address and we'll take you straight to setting up your account.",
    button: "Confirm my email",
    url: confirmUrl("signup"),
    why: "You signed up for Trekly with this address. If this wasn't you, you can ignore this email and no account will be set up.",
  },
  {
    file: "recovery.html",
    subject: "Reset your Trekly password",
    preheader: "Choose a new password for your Trekly account.",
    heading: "Reset your password",
    body: "We got a request to reset the password for your Trekly account. Use the button below to choose a new one.",
    button: "Choose a new password",
    url: confirmUrl("recovery"),
    why: "Someone asked to reset the password for the Trekly account with this address. If this wasn't you, you can ignore this email: your password stays the same.",
  },
  {
    file: "email_change.html",
    subject: "Confirm your new email for Trekly",
    preheader: "Confirm the change to the email address on your Trekly account.",
    heading: "Confirm your new email",
    body: "Your Trekly account's email is changing from <strong>{{ .Email }}</strong> to <strong>{{ .NewEmail }}</strong>. Confirm the change below. If we sent a link to both addresses, open both to finish.",
    button: "Confirm the change",
    url: confirmUrl("email_change"),
    why: "Someone asked to change the email on a Trekly account to or from this address. If this wasn't you, don't open the link, and reset your password.",
  },
  {
    file: "magic_link.html",
    subject: "Your Trekly sign-in link",
    preheader: "Sign in to Trekly without a password.",
    heading: "Sign in to Trekly",
    body: "Here's the sign-in link you asked for. It signs you in to Trekly in this browser, no password needed.",
    button: "Sign in to Trekly",
    url: confirmUrl("magiclink"),
    why: "Someone asked for a sign-in link for the Trekly account with this address. If this wasn't you, you can ignore this email.",
  },
  {
    file: "invite.html",
    subject: "You're invited to Trekly",
    preheader: "Accept your invite and choose a password to get started.",
    heading: "You're invited to Trekly",
    body: "You've been invited to join Trekly, a place to plan backcountry trips, track your gear and keep a trail journal. Accept the invite and choose a password to get started.",
    button: "Accept the invite",
    url: confirmUrl("invite"),
    why: "Someone invited this address to Trekly. If you weren't expecting it, you can ignore this email and no account will be set up.",
  },
  {
    file: "reauthentication.html",
    subject: "Your Trekly verification code",
    preheader: "Enter this code in Trekly to confirm it's you.",
    heading: "Confirm it's you",
    body: "Enter this code in Trekly to finish changing your password.",
    code: "{{ .Token }}",
    why: "You're changing your Trekly password. If this wasn't you, someone may be signed in to your account: reset your password and let us know.",
  },
];

const EXPIRY = "This link works once and expires in an hour.";

function card(t) {
  if (t.code) {
    return `<tr><td style="padding:0 0 8px">
<table role="presentation" cellpadding="0" cellspacing="0" style="background:${CREAM};border-radius:12px">
<tr><td style="padding:14px 22px;font-family:Menlo,Consolas,'Courier New',monospace;font-size:28px;letter-spacing:6px;font-weight:700;color:${INK}">${t.code}</td></tr>
</table>
</td></tr>
<tr><td style="color:${MUTED};font-size:13px;line-height:1.5;padding:8px 0 0">The code expires in an hour. Trekly will never ask you for it by email or phone.</td></tr>`;
  }
  return `<tr><td style="padding:4px 0 18px">
<a href="${t.url}" style="display:inline-block;background:${BUTTON};color:#ffffff;font-weight:600;font-size:15px;text-decoration:none;padding:12px 22px;border-radius:999px">${t.button}</a>
</td></tr>
<tr><td style="color:${MUTED};font-size:13px;line-height:1.5;padding:0 0 4px">Or paste this link into your browser:</td></tr>
<tr><td style="font-size:13px;line-height:1.5;word-break:break-all;padding:0 0 12px"><a href="${t.url}" style="color:${OLIVE}">${t.url}</a></td></tr>
<tr><td style="color:${MUTED};font-size:13px;line-height:1.5">${EXPIRY}</td></tr>`;
}

export function render(t) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>${t.subject}</title>
</head>
<body style="margin:0;padding:0;background:${CREAM};font-family:${SANS};color:${INK}">
<div style="display:none;max-height:0;overflow:hidden">${t.preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${CREAM}">
<tr><td align="center" style="padding:28px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px">
<tr><td style="padding:0 0 18px">
<a href="{{ .SiteURL }}" style="text-decoration:none;color:${INK}">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding:0 10px 0 0;vertical-align:middle"><img src="{{ .SiteURL }}/email/trekly-mark.png" width="32" height="32" alt="Trekly logo" style="display:block;border:0;border-radius:7px"></td>
<td style="vertical-align:middle;font-family:${SERIF};font-size:22px;font-weight:700;color:${INK}">Trekly</td>
</tr></table>
</a>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid ${BORDER};border-radius:16px;padding:26px 24px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="font-family:${SERIF};font-size:24px;line-height:1.25;font-weight:600;color:${INK};padding:0 0 12px">${t.heading}</td></tr>
<tr><td style="color:${INK};font-size:15px;line-height:1.55;padding:0 0 18px">${t.body}</td></tr>
${card(t)}
</table>
</td></tr>
<tr><td style="padding:18px 8px 0;color:${MUTED};font-size:12px;line-height:1.5">
${t.why}<br>
Questions? Email <a href="mailto:${SUPPORT}" style="color:${OLIVE}">${SUPPORT}</a>.
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
`;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const here = dirname(fileURLToPath(import.meta.url));
  for (const t of TEMPLATES) {
    writeFileSync(join(here, t.file), render(t));
    console.log(`${t.file.padEnd(22)} ${t.subject}`);
  }
}
