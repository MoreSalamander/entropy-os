"use client";

import { useState, type FormEvent } from "react";
import Section from "./Section";

export interface ContactFormProps {
  eyebrow?: string;
  heading: string;
  sub?: string;
  /** No backend is wired on purpose: the form validates locally and shows a
   *  confirmation. Point `action` handling at a real endpoint at launch —
   *  the generated site never posts user data anywhere by default. */
  fields?: { emailLabel: string; nameLabel: string; messageLabel: string; submitLabel: string };
}

const DEFAULT_FIELDS = {
  emailLabel: "Work email",
  nameLabel: "Full name",
  messageLabel: "How can we help?",
  submitLabel: "Send message",
};

export default function ContactForm({ eyebrow, heading, sub, fields = DEFAULT_FIELDS }: ContactFormProps) {
  const [sent, setSent] = useState(false);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSent(true);
  }

  return (
    <Section eyebrow={eyebrow} heading={heading} sub={sub}>
      <div className="mx-auto max-w-xl">
        {sent ? (
          <p role="status" className="rounded-token border border-accent/40 bg-surface p-6 text-center text-text">
            Thanks — your message is noted. (Demo form: connect a real endpoint before launch.)
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label htmlFor="contact-name" className="mb-1.5 block text-sm font-medium text-text">
                {fields.nameLabel}
              </label>
              <input
                id="contact-name"
                name="name"
                type="text"
                required
                autoComplete="name"
                className="w-full rounded-token border border-surface bg-surface px-4 py-2.5 text-text outline-none transition-colors focus:border-accent"
              />
            </div>
            <div>
              <label htmlFor="contact-email" className="mb-1.5 block text-sm font-medium text-text">
                {fields.emailLabel}
              </label>
              <input
                id="contact-email"
                name="email"
                type="email"
                required
                autoComplete="email"
                className="w-full rounded-token border border-surface bg-surface px-4 py-2.5 text-text outline-none transition-colors focus:border-accent"
              />
            </div>
            <div>
              <label htmlFor="contact-message" className="mb-1.5 block text-sm font-medium text-text">
                {fields.messageLabel}
              </label>
              <textarea
                id="contact-message"
                name="message"
                rows={5}
                required
                className="w-full rounded-token border border-surface bg-surface px-4 py-2.5 text-text outline-none transition-colors focus:border-accent"
              />
            </div>
            <button
              type="submit"
              className="w-full rounded-token bg-accent px-5 py-3 font-medium text-background transition-opacity hover:opacity-90"
            >
              {fields.submitLabel}
            </button>
          </form>
        )}
      </div>
    </Section>
  );
}
