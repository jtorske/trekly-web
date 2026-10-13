"use strict";

/**
 * One-off SendGrid pipeline check — not part of the job system. Run with:
 *
 *   node scripts/test-email.js
 *
 * Loads SENDGRID_API_KEY / SENDGRID_FROM_EMAIL from this service's own
 * .env (campalert-service/.env, copied from .env.example — see there for
 * why this is intentionally separate from the Python backend's .env).
 * Neither value is ever hardcoded here — only the recipient below is, on
 * purpose, since this is a manual one-off check, not a reusable tool.
 */

require("dotenv").config();
const sgMail = require("@sendgrid/mail");

// Fill in the address to send the test to before running.
const TEST_RECIPIENT_EMAIL = "jtorske27@gmail.com";

const apiKey = process.env.SENDGRID_API_KEY;
const fromEmail = process.env.SENDGRID_FROM_EMAIL;
const toEmail = TEST_RECIPIENT_EMAIL;

if (!apiKey || !fromEmail) {
  console.error(
    "Missing SENDGRID_API_KEY and/or SENDGRID_FROM_EMAIL in campalert-service/.env " +
      "(copy .env.example to .env and fill them in).",
  );
  process.exit(1);
}

if (!toEmail) {
  console.error(
    "Set TEST_RECIPIENT_EMAIL at the top of scripts/test-email.js before running.",
  );
  process.exit(1);
}

sgMail.setApiKey(apiKey);

sgMail
  .send({
    to: toEmail,
    from: fromEmail,
    subject: "CampAlert — SendGrid test",
    text: "If you're reading this, the CampAlert SendGrid pipeline works end to end.",
    html: "<p>If you're reading this, the CampAlert SendGrid pipeline works end to end.</p>",
  })
  .then(() => {
    console.log(`Sent test email to ${toEmail} from ${fromEmail}.`);
  })
  .catch((err) => {
    console.error("SendGrid send failed:", err.response?.body ?? err.message);
    process.exit(1);
  });
