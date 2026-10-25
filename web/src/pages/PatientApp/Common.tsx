import { useEffect, useRef, type ReactNode } from "react";
import { useLang } from "../../components/i18n";

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  const { t } = useLang();
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} className="toggle" onClick={() => onChange(!on)}>
      <span>{on ? t("on") : t("off")}</span><i />
    </button>
  );
}

export function Confirm({ title, body, yes, no, onYes, onNo, danger }: { title: string; body: string; yes: string; no: string; onYes: () => void; onNo: () => void; danger?: boolean }) {
  const ref = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const onNoRef = useRef(onNo);
  onNoRef.current = onNo;
  useEffect(() => {
    // Remember what had focus (the switch), move focus in, keep Tab inside, give focus back on close.
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onNoRef.current(); return; }
      if (e.key !== "Tab" || !box.current) return;
      const f = Array.from(box.current.querySelectorAll<HTMLElement>("button:not([disabled])"));
      if (f.length === 0) return;
      const first = f[0], last = f[f.length - 1];
      const at = document.activeElement;
      if (!box.current.contains(at)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", k);
    return () => { window.removeEventListener("keydown", k); if (prev && prev.isConnected) prev.focus(); };
  }, []);
  return (
    <div className="dlg-bg">
      <div className="dlg" ref={box} role="alertdialog" aria-modal="true" aria-labelledby="dlg-t" aria-describedby="dlg-b">
        <h2 id="dlg-t">{title}</h2>
        <p id="dlg-b">{body}</p>
        <div className="actions">
          <button type="button" ref={ref} className="btn ghost" onClick={onNo}>{no}</button>
          <button type="button" className={`btn${danger ? " danger" : ""}`} onClick={onYes}>{yes}</button>
        </div>
      </div>
    </div>
  );
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return <div className="empty"><b>{title}</b>{body}</div>;
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return <a className="nl" href={to}>‹ {children}</a>;
}
