# EXECUTION CONTRACT (MANDATORY)

## CRITICAL NOTICE

This document is not a suggestion.

It is a mandatory engineering specification.

Every requirement inside this document MUST be followed.

Skipping, simplifying, assuming, or partially implementing any requirement is considered an implementation failure.

The implementation is only considered COMPLETE when every requirement has been satisfied and verified.

---

# ABSOLUTE REQUIREMENTS

The following actions are STRICTLY FORBIDDEN.

❌ Starting coding before understanding the project.

❌ Modifying code without understanding dependencies.

❌ Breaking existing features.

❌ Guessing project architecture.

❌ Removing existing functionality.

❌ Introducing regressions.

❌ Introducing duplicated logic.

❌ Writing temporary solutions.

❌ Writing placeholder implementations.

❌ Leaving TODO/FIXME comments.

❌ Ignoring validation.

❌ Ignoring error handling.

❌ Returning unfinished implementation.

If any of the above occurs, the implementation is considered FAILED.

---

# ENTERPRISE QUALITY STANDARD

The implementation quality must meet the expectations of a medium-sized production system.

Every line of code must satisfy:

• correctness

• maintainability

• scalability

• security

• consistency

• readability

The objective is not to make the code "work".

The objective is to make the system reliable for real users.

---

# ZERO REGRESSION POLICY

The authentication implementation must not reduce the stability of any existing feature.

Before changing any file:

Analyze all dependencies.

After changing any file:

Verify every dependent feature.

No regression is acceptable.

---

# PROJECT SAFETY RULE

Never modify code simply because it "looks unnecessary".

If a piece of code appears unused:

First verify whether:

- another route uses it

- middleware uses it

- template uses it

- JavaScript uses it

- background task uses it

- scheduled task uses it

- external API uses it

Never remove code based on assumptions.

---

# DATABASE SAFETY

Database consistency has higher priority than implementation speed.

Never:

- bypass constraints

- disable validation

- remove indexes

- remove unique constraints

- overwrite production data

Every migration must preserve existing users.

---

# API STABILITY

Every authentication API must be deterministic.

Given the same valid input:

The API must always return the expected result.

Unexpected behavior is unacceptable.

---

# BACKWARD COMPATIBILITY

The existing project is considered production software.

Authentication improvements must integrate into the project.

Not replace it.

No existing API should unexpectedly change behavior.

---

# SELF VERIFICATION

Before declaring the implementation complete, perform an internal verification.

Verify:

✓ every endpoint

✓ every middleware

✓ every database constraint

✓ every validation

✓ every OAuth flow

✓ every password flow

✓ every token flow

✓ every session flow

✓ every permission

✓ every error response

✓ every logout flow

✓ every refresh flow

If any verification fails:

The implementation is NOT complete.

---

# INTERNAL QUALITY REVIEW

Review your own implementation as if another senior engineer will audit it.

Look for:

- duplicated code

- race conditions

- null references

- inconsistent naming

- security weaknesses

- missing validation

- missing indexes

- missing transactions

- missing rollback handling

- missing exception handling

Correct every issue before finishing.

---

# NO ASSUMPTIONS RULE

Never assume.

If project behavior cannot be inferred from the codebase:

Analyze more.

If still uncertain:

Clearly state the uncertainty instead of inventing behavior.

---

# PRODUCTION SECURITY

Treat every request as potentially malicious.

Validate everything.

Trust nothing from the client.

Never expose:

- passwords

- hashes

- tokens

- secrets

- internal stack traces

- internal file paths

- SQL queries

- implementation details

---

# RELIABILITY REQUIREMENT

Authentication failures must fail safely.

Security is always more important than convenience.

When uncertainty exists:

Prefer rejecting the request rather than accepting unsafe behavior.

---

# COMPLETION CRITERIA

The implementation is considered complete ONLY IF:

✓ All requirements are implemented.

✓ Existing functionality remains intact.

✓ Authentication flows work correctly.

✓ Security requirements are satisfied.

✓ Database integrity is preserved.

✓ No regression has been introduced.

✓ Code passes self-review.

✓ The implementation is suitable for deployment in a medium-sized production environment.

Only after all these conditions are met may the implementation be marked as COMPLETE.
# AUTHENTICATION SYSTEM REQUIREMENTS

Version: 1.0
Priority: CRITICAL
Status: REQUIRED

---

# OBJECTIVE

Design and implement a production-grade Authentication & Authorization backend with an architecture comparable to modern authentication providers such as Clerk.

This implementation must be completely self-hosted and integrated into the existing project without breaking any current functionality.

The authentication system must prioritize:

- Security
- Stability
- Scalability
- Maintainability
- High Performance
- Backward Compatibility

Every change must be production-ready.

---

# MANDATORY PRE-DEVELOPMENT PROCESS

Before modifying any source file, you MUST:

1. Read the entire project.
2. Understand the complete architecture.
3. Identify every authentication-related module.
4. Understand all API flows.
5. Understand the database schema.
6. Understand session handling.
7. Understand frontend authentication flow.
8. Understand existing middleware.
9. Understand authorization logic.
10. Build a dependency map.

DO NOT start coding until the complete analysis has finished.

---

# ARCHITECTURE REQUIREMENTS

Authentication must be separated into independent modules.

Example:

auth/
    providers/
    middleware/
    tokens/
    validators/
    services/
    repositories/
    models/
    utils/
    api/

Every module must have a single responsibility.

Business logic must never be mixed inside routes.

---

# API DESIGN

The authentication system must expose its own dedicated API.

Examples:

POST /api/auth/register

POST /api/auth/login

POST /api/auth/google

POST /api/auth/logout

GET /api/auth/me

POST /api/auth/refresh

POST /api/auth/verify

POST /api/auth/change-password

POST /api/auth/request-password-reset

POST /api/auth/reset-password

GET /api/auth/session

POST /api/auth/check-username

POST /api/auth/check-email

GET /api/auth/providers

POST /api/auth/link-google

POST /api/auth/unlink-google

Every API must:

- validate input
- validate permissions
- return proper HTTP codes
- return structured JSON
- never expose internal errors

---

# ACCOUNT SYSTEM

Each account may have:

- one unique ID
- one username
- one Gmail account
- one encrypted password (if applicable)

One Gmail can only belong to one account.

One username can only belong to one account.

Duplicate accounts are strictly forbidden.

---

# USERNAME RULES

Username must:

- be globally unique
- ignore uppercase/lowercase
- ignore leading/trailing spaces
- pass format validation
- be indexed
- be checked before insertion
- be checked before update

Database must enforce UNIQUE constraints.

Application must also validate uniqueness.

---

# EMAIL RULES

Only Gmail addresses are accepted.

Requirements:

- lowercase
- trimmed
- validated
- unique

Database UNIQUE constraint is mandatory.

---

# GOOGLE AUTH

Google OAuth must:

- verify ID Token
- verify issuer
- verify audience
- verify expiration
- verify signature
- retrieve Google Subject ID
- retrieve Gmail
- retrieve avatar
- retrieve display name

If Gmail exists:

→ login

If Gmail does not exist:

→ create account

Never create duplicate users.

---

# PASSWORD SECURITY

Passwords must:

- never be stored as plaintext
- be hashed using Argon2id or bcrypt
- include salt
- be verified securely

No custom hashing algorithms.

---

# TOKEN SYSTEM

Implement a secure token architecture.

Requirements:

- Access Token
- Refresh Token
- Rotation
- Expiration
- Revocation
- Replay protection

Expired tokens must never be accepted.

---

# SESSION MANAGEMENT

Support:

- login
- logout
- logout all devices
- session validation
- session expiration
- session renewal

Inactive sessions should expire automatically.

---

# EMAIL SERVICE

Automatically send an email after successful account creation.

Email must include:

- welcome message
- username
- Gmail
- account creation time
- device (if available)
- IP address (if available)
- security notice

HTML email must be responsive.

---

# AUTHORIZATION

Authentication and Authorization must remain independent.

Authentication:

Who is the user?

Authorization:

What is the user allowed to do?

Never mix these responsibilities.

---

# SECURITY REQUIREMENTS

The system must implement:

- CSRF protection (if cookie-based)
- Rate limiting
- Brute-force protection
- SQL injection protection
- XSS protection
- Input sanitization
- Secure Cookies
- HttpOnly
- SameSite
- HTTPS ready
- Security headers
- Constant-time password comparison
- Account enumeration protection
- Audit logging for authentication events

---

# DATABASE REQUIREMENTS

Database must contain constraints for:

- username UNIQUE
- email UNIQUE
- google_sub UNIQUE

Create indexes for frequently queried fields.

Never rely solely on application logic for uniqueness.

---

# VALIDATION

Validate every incoming request.

This includes:

- JSON body
- Query parameters
- Headers
- Cookies
- OAuth callbacks
- Tokens
- Uploaded data

Never trust client input.

---

# ERROR HANDLING

Never expose stack traces.

Use standardized JSON responses.

Example:

{
    "success": false,
    "code": "USERNAME_EXISTS",
    "message": "Username already exists."
}

---

# LOGGING

Authentication events must be logged.

Include:

- login
- logout
- failed login
- account creation
- password reset
- Google OAuth
- suspicious activity

Sensitive information must never be written to logs.

---

# PERFORMANCE

Authentication endpoints should be lightweight.

Avoid unnecessary database queries.

Cache immutable configuration when appropriate.

Prevent N+1 query issues.

---

# BACKWARD COMPATIBILITY

Existing project functionality must continue working.

No current feature may break.

Existing APIs must continue functioning unless explicitly replaced.

---

# TESTING

Before considering implementation complete:

- verify every endpoint
- verify every validation rule
- verify duplicate prevention
- verify Google login
- verify username login
- verify email login
- verify session expiration
- verify logout
- verify refresh flow
- verify security protections

No feature is considered complete without testing.

---

# CODE QUALITY

Code must be:

- modular
- maintainable
- documented
- strongly typed where applicable
- readable
- reusable

Avoid duplicated logic.

---

# FINAL REQUIREMENT

Before finishing:

1. Re-scan the project.
2. Verify all authentication flows.
3. Ensure no regression has been introduced.
4. Ensure database consistency.
5. Ensure security requirements are satisfied.
6. Ensure every endpoint behaves correctly.
7. Ensure no existing user functionality has been negatively affected.

Only then is the implementation considered complete.
