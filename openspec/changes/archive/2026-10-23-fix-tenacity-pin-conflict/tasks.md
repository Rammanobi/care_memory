# Tasks

- [x] Reproduce: `uv pip compile requirements.txt --python-version 3.12` reports tenacity conflict (`requirements.txt`)
- [x] Replace `tenacity==9.2.1` with `tenacity>=8.2.3,<9.2.0` (`requirements.txt`)
- [x] Add the transitive-dependency and `uv` note (`requirements.txt`)
- [x] Verify: `uv pip compile requirements.txt --python-version 3.12` exits 0 (tenacity 9.1.4)
