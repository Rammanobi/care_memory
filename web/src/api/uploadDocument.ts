// The upload call. Live: multipart POST /portal/documents (field "file") with progress. Mock mode: a fake upload that adds a
// document with status "with your care team", so the whole flow can be shown offline.
import { USE_MOCK } from "./index";
import { API_BASE, NetworkError, problemFrom } from "./http";
import { getExtras, setExtras } from "./patientExtras";
import type { UploadResult } from "./documents";

export function uploadDocument(file: File, onProgress: (pct: number) => void): Promise<UploadResult> {
  return USE_MOCK ? mockUpload(file, onProgress) : liveUpload(file, onProgress);
}

// XMLHttpRequest because fetch cannot report upload progress.
function liveUpload(file: File, onProgress: (pct: number) => void): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", new URL(API_BASE + "/portal/documents", location.origin).toString());
    x.withCredentials = true;
    x.setRequestHeader("Accept", "application/json");
    x.setRequestHeader("X-CM-Client", "web");
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.min(99, Math.round((e.loaded / e.total) * 100))); };
    x.onerror = () => reject(new NetworkError("Network error"));
    x.ontimeout = () => reject(new NetworkError("Timed out"));
    x.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status < 200 || x.status >= 300) return reject(problemFrom(x.status, body));
      const b = (body ?? {}) as Record<string, unknown>;
      if (typeof b.document_id !== "string") return reject(problemFrom(500, null));
      onProgress(100);
      resolve({ documentId: b.document_id, status: typeof b.status === "string" ? b.status : "", duplicate: !!b.duplicate });
    };
    const fd = new FormData();
    fd.append("file", file);
    x.send(fd);
  });
}

function mockUpload(file: File, onProgress: (pct: number) => void): Promise<UploadResult> {
  return new Promise((resolve) => {
    let p = 0;
    const tick = window.setInterval(() => {
      p = Math.min(100, p + 25);
      onProgress(p);
      if (p < 100) return;
      window.clearInterval(tick);
      const have = getExtras().docs;
      const dup = have.some((d) => d.title === file.name && d.size === file.size);
      const id = `mock-doc-${Date.now()}`;
      if (!dup) setExtras({ docs: [{ id, title: file.name, kind: "other", date: new Date().toISOString().slice(0, 10), summary: "", status: "with your care team", size: file.size }, ...have] });
      resolve({ documentId: id, status: "with your care team", duplicate: dup });
    }, 120);
  });
}
