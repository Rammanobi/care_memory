# fix-tenacity-pin-conflict

**Lane:** I (infra, `requirements.txt`). **Spec section:** feature_specs/04 section 11 (requirements).

## Symptom
`pip install --dry-run -r requirements.txt` failed with `resolution-too-deep` (exit 1). `uv pip compile` showed the real conflict:
`tenacity==9.2.1` is unsatisfiable.

## Root cause
`deepagents==0.7.30` depends on `langchain-google-genai>=4.4.2`, which depends on `google-genai>=2.20.0`, which requires `tenacity>=8.2.3,<9.2.0`. Our exact pin `tenacity==9.2.1` sits outside that range.

## Fix
Replace the pin with `tenacity>=8.2.3,<9.2.0`. Add a comment that `deepagents` installs `langchain-anthropic` and `langchain-google-genai` transitively (installed but unused; runtime models stay OpenAI or DeepSeek only), and that `uv pip install` is preferred.

## Verification
`uv pip compile requirements.txt --python-version 3.12` exits 0 and resolves `tenacity==9.1.4`, `deepagents==0.7.30`, `langgraph==1.2.16`, `langchain-openai==1.7.2`, `langchain-deepseek==1.1.1`.

## Out of scope
Install-testing every pin on Python 3.12 with `uv pip install`; the `UNVERIFIED` labels on other pins stay until each lane runs its tests.
