## ADDED Requirements

### Requirement: Firebase sign-in and bearer tokens in the web app
With `VITE_AUTH_MODE=firebase` the web app SHALL sign in with the Firebase Web SDK (email/password, username mapped to `<username>@<VITE_AUTH_EMAIL_DOMAIN>`), SHALL send `Authorization: Bearer <ID token>` on every API call and document upload without cookies, SHALL retry once with a forced token refresh on 401, and SHALL sign out of Firebase on logout.

#### Scenario: Authenticated call
- **WHEN** a signed-in doctor loads the review queue
- **THEN** the request carries a bearer ID token and `credentials` is `omit`

#### Scenario: Expired token
- **WHEN** an API call returns 401
- **THEN** the adapter refreshes the ID token once and repeats the call, and signs the user out if it fails again

#### Scenario: Sign-out
- **WHEN** the user clicks sign out
- **THEN** the Firebase session ends and the app returns to the login page
