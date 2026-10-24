#!/usr/bin/env bash
# Global external HTTPS load balancer in front of Cloud Run cm-api (DEPLOY_PLAN sections 1.2, 1.3, 1.5).
# Creates: static IP, serverless NEG, backend service, URL map with per-host "/" redirects, one managed
# certificate for apex/doctor./patient./family./demo., HTTPS proxy + forwarding rule, HTTP->HTTPS redirect.
# Usage: DOMAIN=example.org bash infra/85_lb.sh     (DRY_RUN=1 to print the gcloud calls only)
# Needs a cm-api service to exist (a placeholder deploy is enough). Idempotent: existing resources are kept.
# After it runs, add DNS A records for every hostname to the printed IP; the cert turns ACTIVE after DNS resolves.
set -euo pipefail
source "$(dirname "$0")/vars.sh"
need_domain
exists() { gcloud "$@" >/dev/null 2>&1; }
[ "$DRY_RUN" = "1" ] && exists() { return 1; }

exists compute addresses describe cm-ip --global || gcloud compute addresses create cm-ip --global --ip-version=IPV4
exists compute network-endpoint-groups describe cm-neg --region="$REGION" || \
  gcloud compute network-endpoint-groups create cm-neg --region="$REGION" \
    --network-endpoint-type=serverless --cloud-run-service=cm-api
if ! exists compute backend-services describe cm-api-be --global; then
  gcloud compute backend-services create cm-api-be --global --load-balancing-scheme=EXTERNAL_MANAGED \
    --protocol=HTTPS
  gcloud compute backend-services add-backend cm-api-be --global \
    --network-endpoint-group=cm-neg --network-endpoint-group-region="$REGION"
fi

# URL map: every host -> cm-api-be; "/" on each landing host redirects to its SPA area.
URLMAP="$(mktemp)"
REDIR="$(mktemp)"
trap 'rm -f "$URLMAP" "$REDIR"' EXIT
BE="projects/$PROJECT/global/backendServices/cm-api-be"
pm() { echo "pm-${1%%.*}-$(echo "$1" | cksum | cut -d' ' -f1)"; }
{
  echo "name: cm-urlmap"
  echo "defaultService: $BE"
  echo "hostRules:"
  for h in $(hosts); do echo "- hosts: ['$h']"; echo "  pathMatcher: $(pm "$h")"; done
  echo "pathMatchers:"
  for h in $(hosts); do
    case "$h" in
      doctor.*|demo.*) land=/doctor ;;
      patient.*) land=/patient ;;
      family.*) land=/supporter ;;
      *) land="" ;;
    esac
    echo "- name: $(pm "$h")"
    echo "  defaultService: $BE"
    if [ -n "$land" ]; then
      echo "  routeRules:"
      echo "  - priority: 1"
      echo "    matchRules: [{fullPathMatch: /}]"
      echo "    urlRedirect: {pathRedirect: $land, redirectResponseCode: FOUND, stripQuery: false}"
    fi
  done
} > "$URLMAP"
exists compute url-maps describe cm-urlmap --global || \
  gcloud compute url-maps create cm-urlmap --global --default-service=cm-api-be
gcloud compute url-maps import cm-urlmap --global --source="$URLMAP" --quiet

# Managed cert: ONE cert for all names. If a host never resolves, the whole cert stays PROVISIONING.
DOMAINS=$(hosts | tr ' ' ',')
exists compute ssl-certificates describe cm-cert --global || \
  gcloud compute ssl-certificates create cm-cert --global --domains="$DOMAINS"
exists compute target-https-proxies describe cm-https-proxy --global || \
  gcloud compute target-https-proxies create cm-https-proxy --global --url-map=cm-urlmap --ssl-certificates=cm-cert
exists compute forwarding-rules describe cm-https-fr --global || \
  gcloud compute forwarding-rules create cm-https-fr --global --load-balancing-scheme=EXTERNAL_MANAGED \
    --address=cm-ip --target-https-proxy=cm-https-proxy --ports=443

# HTTP :80 -> HTTPS redirect (separate URL map, same IP).
printf 'name: cm-http-redirect\ndefaultUrlRedirect:\n  redirectResponseCode: MOVED_PERMANENTLY_DEFAULT\n  httpsRedirect: true\n' > "$REDIR"
exists compute url-maps describe cm-http-redirect --global || \
  gcloud compute url-maps import cm-http-redirect --global --source="$REDIR" --quiet
exists compute target-http-proxies describe cm-http-proxy --global || \
  gcloud compute target-http-proxies create cm-http-proxy --global --url-map=cm-http-redirect
exists compute forwarding-rules describe cm-http-fr --global || \
  gcloud compute forwarding-rules create cm-http-fr --global --load-balancing-scheme=EXTERNAL_MANAGED \
    --address=cm-ip --target-http-proxy=cm-http-proxy --ports=80

IP=$(gcloud compute addresses describe cm-ip --global --format='value(address)')
echo "85_lb: done. Add DNS A records (TTL 300) pointing to ${IP:-<cm-ip>}:"
for h in $(hosts); do echo "  A  $h -> ${IP:-<cm-ip>}"; done
echo "Remove AAAA/parking records on those names. Cert status:"
echo "  gcloud compute ssl-certificates describe cm-cert --global --format='value(managed.status)'"
