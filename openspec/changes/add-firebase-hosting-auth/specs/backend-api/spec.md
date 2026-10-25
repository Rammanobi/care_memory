## ADDED Requirements

### Requirement: Selectable authentication mode
The API SHALL support `AUTH_MODE=local` (default: scrypt login and HS256 session cookie, unchanged) and `AUTH_MODE=firebase` (Firebase ID token bearer only), and SHALL refuse to start in firebase mode without `FIREBASE_PROJECT_ID`.

#### Scenario: Local mode unchanged
- **WHEN** `AUTH_MODE` is unset
- **THEN** `POST /auth/login` issues the `cm_session` cookie exactly as before and all existing auth tests pass

#### Scenario: Password login disabled in firebase mode
- **WHEN** `AUTH_MODE=firebase` and a client calls `POST /auth/login`
- **THEN** the API answers 404 with code `use_firebase`

### Requirement: Firebase ID token verification
In firebase mode the API SHALL accept a request only with an RS256 Firebase ID token signed by a current Google securetoken key, with `aud` equal to the project id, `iss` equal to `https://securetoken.google.com/<project>`, a non-empty `sub`, and an unexpired `exp`; any failure SHALL answer 401 `unauthenticated`.

#### Scenario: Token for another project
- **WHEN** a valid Firebase token whose `aud` is another project is presented
- **THEN** the API answers 401

#### Scenario: Wrong algorithm
- **WHEN** a token with `alg` HS256 or none is presented
- **THEN** the API answers 401

### Requirement: Roles come from the database, not the client
In firebase mode the API SHALL read `role`, `pid` and `tv` custom claims and SHALL allow the request only when the person exists, the credential is active, the stored role equals the claim and the stored token_version equals `tv`; a token without these claims SHALL answer 403 `no_role`.

#### Scenario: Retired user with a valid token
- **WHEN** a user whose `auth_credentials.active` is false presents an unexpired valid token
- **THEN** the API answers 401

#### Scenario: Revoked by token_version bump
- **WHEN** an admin bumps the user's token_version and the user presents a token carrying the old `tv`
- **THEN** the API answers 401

#### Scenario: Self-created account without claims
- **WHEN** a Firebase user with no custom claims calls `GET /auth/me`
- **THEN** the API answers 403 `no_role`
