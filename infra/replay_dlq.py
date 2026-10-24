"""Replay dead-lettered Gmail push messages from dead-letter-sub back to gmail-push.

Usage: python infra/replay_dlq.py PROJECT [--max 100]
Requires google-cloud-pubsub (requirements-dev.txt). Messages are re-published then acked; the receiving
handler is idempotent (task name gmail-fetch-{historyId}), so replays are safe.
"""
import argparse

from google.cloud import pubsub_v1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("project")
    p.add_argument("--max", type=int, default=100)
    a = p.parse_args()
    sub = pubsub_v1.SubscriberClient()
    pub = pubsub_v1.PublisherClient()
    sub_path = sub.subscription_path(a.project, "dead-letter-sub")
    topic = pub.topic_path(a.project, "gmail-push")
    resp = sub.pull(request={"subscription": sub_path, "max_messages": a.max})
    ack_ids = []
    for m in resp.received_messages:
        pub.publish(topic, m.message.data, **dict(m.message.attributes)).result()
        ack_ids.append(m.ack_id)
    if ack_ids:
        sub.acknowledge(request={"subscription": sub_path, "ack_ids": ack_ids})
    print(f"replayed {len(ack_ids)} message(s)")


if __name__ == "__main__":
    main()
