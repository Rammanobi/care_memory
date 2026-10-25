// Firebase Auth sign-in path, used ONLY when VITE_AUTH_MODE=firebase (FIREBASE_PLAN.md 2.4).
// The SDK is imported lazily, so local mode (the default: /auth/login + cm_session cookie) never loads it.
// The web config (VITE_FIREBASE_*) is public by design; it is not a secret.

/** Read per call (not cached) so tests can stub the env. Anything but "firebase" means local. */
export const isFirebaseMode = (): boolean => import.meta.env.VITE_AUTH_MODE === "firebase";

/** The login form keeps "username"; Firebase needs an email: <username>@<VITE_AUTH_EMAIL_DOMAIN>. */
export function emailFor(username: string, domain = (import.meta.env.VITE_AUTH_EMAIL_DOMAIN as string | undefined) ?? "users.carememory.app"): string {
  const u = username.trim().toLowerCase();
  return u.includes("@") ? u : `${u}@${domain}`;
}

/** The slice of Firebase Auth the app uses; tests inject a fake. */
export interface FirebaseAuthApi {
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  /** Current user's ID token (SDK refreshes near expiry); force=true always refreshes. null = signed out. */
  getIdToken(force?: boolean): Promise<string | null>;
}

let loaded: Promise<FirebaseAuthApi> | null = null;

export function setFirebaseAuthForTests(api: FirebaseAuthApi | null): void {
  loaded = api ? Promise.resolve(api) : null;
}

export function firebaseAuth(): Promise<FirebaseAuthApi> {
  if (!loaded) loaded = loadSdk();
  return loaded;
}

async function loadSdk(): Promise<FirebaseAuthApi> {
  const [{ initializeApp, getApps }, fa] = await Promise.all([import("firebase/app"), import("firebase/auth")]);
  const env = import.meta.env;
  const app = getApps()[0] ?? initializeApp({
    apiKey: env.VITE_FIREBASE_API_KEY as string,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN as string,
    projectId: env.VITE_FIREBASE_PROJECT_ID as string,
    appId: env.VITE_FIREBASE_APP_ID as string,
  });
  const auth = fa.getAuth(app);
  // Tab-scoped by default (staff, shared machines); VITE_FIREBASE_PERSISTENCE=local keeps patients signed in.
  await fa.setPersistence(auth, env.VITE_FIREBASE_PERSISTENCE === "local" ? fa.browserLocalPersistence : fa.browserSessionPersistence);
  await auth.authStateReady();
  return {
    async signIn(email, password) {
      await fa.signInWithEmailAndPassword(auth, email, password);
    },
    signOut: () => fa.signOut(auth),
    async getIdToken(force = false) {
      return auth.currentUser ? auth.currentUser.getIdToken(force) : null;
    },
  };
}

/** Bearer header for the current Firebase user, or {} when signed out / in local mode. */
export async function bearerHeader(force = false): Promise<Record<string, string>> {
  if (!isFirebaseMode()) return {};
  const tok = await (await firebaseAuth()).getIdToken(force);
  return tok ? { Authorization: `Bearer ${tok}` } : {};
}
