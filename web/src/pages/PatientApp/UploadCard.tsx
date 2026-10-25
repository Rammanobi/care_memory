// "Upload a document" card on the Record > Documents tab. Checks the file here first, shows progress, then a calm result.
import { useRef, useState } from "react";
import { useLang } from "../../components/i18n";
import { ACCEPT, IMAGE_ACCEPT, uploadProblemFrom, validateUpload, type UploadProblem } from "../../api/documents";
import { NetworkError } from "../../api/http";
import { uploadDocument } from "../../api/uploadDocument";

type S = { k: "idle" } | { k: "sending"; pct: number; name: string } | { k: "sent"; dup: boolean } | { k: "error"; key: UploadProblem };

export function UploadCard() {
  const { t } = useLang();
  const [s, setS] = useState<S>({ k: "idle" });
  const pick = useRef<HTMLInputElement>(null);
  const cam = useRef<HTMLInputElement>(null);
  const busy = s.k === "sending";

  const go = async (f: File | undefined) => {
    if (!f) return;
    const bad = validateUpload(f);
    if (bad) return setS({ k: "error", key: bad });
    setS({ k: "sending", pct: 0, name: f.name });
    try {
      const r = await uploadDocument(f, (pct) => setS({ k: "sending", pct, name: f.name }));
      setS({ k: "sent", dup: r.duplicate });
      window.dispatchEvent(new Event("cm-session")); // reload the documents list
    } catch (e) {
      setS({ k: "error", key: uploadProblemFrom(e, e instanceof NetworkError) });
    }
  };
  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; e.target.value = ""; void go(f); };
  const btn = { minHeight: 44, height: 48, width: "auto", flex: "1 1 160px", fontSize: 16 } as const;

  return (
    <section className="card" aria-labelledby="up-t" style={{ marginBottom: 10 }}>
      <div className="k" id="up-t">{t("upTitle")}</div>
      <div className="s" style={{ marginBottom: 10 }}>{t("upBody")}</div>
      <input ref={cam} type="file" accept={IMAGE_ACCEPT} capture="environment" onChange={onChange} hidden />
      <input ref={pick} type="file" accept={ACCEPT} onChange={onChange} hidden />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="btn" style={btn} disabled={busy} onClick={() => cam.current?.click()}>{t("upPhoto")}</button>
        <button type="button" className="btn ghost" style={btn} disabled={busy} onClick={() => pick.current?.click()}>{t("upChoose")}</button>
      </div>
      <div className="s" style={{ marginTop: 8 }}>{t("upHint")}</div>
      <div role="status" aria-live="polite" style={{ marginTop: 8 }}>
        {s.k === "sending" && (
          <div className="wait" style={{ marginBottom: 0 }}>
            <b>{t("upSending", { n: s.pct })}</b>
            <div style={{ overflowWrap: "anywhere" }}>{s.name}</div>
            <progress max={100} value={s.pct} style={{ width: "100%" }} aria-label={t("upSending", { n: s.pct })} />
          </div>
        )}
        {s.k === "sent" && <div className="wait" style={{ marginBottom: 0 }}><span className="badge a">✓ {s.dup ? t("upDup") : t("upSent")}</span></div>}
        {s.k === "error" && <div className="wait" style={{ marginBottom: 0 }}><span className="badge c">{t(s.key)}</span></div>}
      </div>
    </section>
  );
}
