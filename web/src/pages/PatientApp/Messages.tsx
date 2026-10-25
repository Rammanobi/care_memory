import { useEffect, useRef, useState } from "react";
import { useLang } from "../../components/i18n";
import { dayDate, type Msg } from "./portalTypes";
import { usePortal } from "./usePortal";
import { Empty } from "./Common";

export const fmtDay = (n: number, lang: string) => dayDate(n).toLocaleDateString(lang === "te" ? "te-IN" : "en-IN", { day: "numeric", month: "short" });

/** Message date: the server timestamp when there is one, otherwise "n days ago" of the sample data. */
export const fmtMsgDay = (m: Msg, lang: string) =>
  m.date ? m.date.toLocaleDateString(lang === "te" ? "te-IN" : "en-IN", { day: "numeric", month: "short" }) : fmtDay(m.daysAgo, lang);

export function useMessages(): { list: Msg[]; isRead: (id: string) => boolean; markRead: (id: string) => void } {
  const v = usePortal();
  return { list: v.messages, isRead: v.isRead, markRead: v.markRead };
}

export default function Messages() {
  const { t, lang } = useLang();
  const { list, isRead, markRead } = useMessages();
  const [open, setOpen] = useState<string | null>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const readRef = useRef<HTMLSpanElement>(null);
  const lastOpened = useRef<string | null>(null);
  const wasRead = useRef(false);
  const m = list.find((x) => x.id === open);
  const unread = list.filter((x) => !isRead(x.id)).length;
  const readNow = m ? isRead(m.id) : false;

  // Focus follows the screen: opening a message focuses its title; closing returns to the row; "Mark as read" lands on "Read".
  useEffect(() => {
    if (open) { lastOpened.current = open; title.current?.focus(); wasRead.current = readNow; }
    else if (lastOpened.current) { document.querySelector<HTMLElement>(`[data-mid="${CSS.escape(lastOpened.current)}"]`)?.focus(); lastOpened.current = null; }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => {
    if (open && readNow && !wasRead.current) readRef.current?.focus();
    wasRead.current = readNow;
  }, [readNow, open]);

  if (m) {
    return (
      <>
        <button type="button" className="link" style={{ paddingLeft: 0 }} onClick={() => setOpen(null)}>‹ {t("backList")}</button>
        <article className="card msg" aria-labelledby="mt">
          <small>{t("fromTeam")} · {fmtMsgDay(m, lang)}</small>
          {m.inReplyTo && <div className="inrep thread">{t("inReplyTo")} "{m.inReplyTo.excerpt}"</div>}
          <h1 id="mt" ref={title} tabIndex={-1} style={{ fontSize: 22 }}>{m.title}</h1>
          <p style={{ margin: "8px 0", fontSize: 18 }}>{m.text}</p>
          <span className="badge a">✓ {t("apprBy")}</span>
          <div style={{ marginTop: 14 }}>
            {isRead(m.id) ? <span className="s" ref={readRef} tabIndex={-1}>✓ {t("readS")}</span> : <button type="button" className="btn" onClick={() => markRead(m.id)}>{t("markRead")}</button>}
          </div>
        </article>
      </>
    );
  }
  return (
    <>
      <h1>{t("messages")}</h1>
      <div className="sub">{unread > 0 ? t("newN", { n: unread }) : t("apprBy")}</div>
      {list.length === 0 ? <Empty title={t("noMsgs")} body={t("noMsgsS")} /> : (
        <div role="list">
          {list.map((x) => {
            const r = isRead(x.id);
            return (
              <button key={x.id} data-mid={x.id} type="button" role="listitem" className={`item${r ? "" : " unread"}`} onClick={() => setOpen(x.id)} aria-label={`${r ? "" : t("unread") + ". "}${x.title}`}>
                <span className={`dot${r ? " r" : ""}`} aria-hidden="true" />
                <span className="tx">{x.inReplyTo && <span className="inrep">{t("inReplyTo")} "{x.inReplyTo.excerpt}"</span>}<b>{x.title}</b><span>{fmtMsgDay(x, lang)} · {x.text}</span></span>
                {!r && <span className="badge u">{t("unread")}</span>}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}
