## ADDED Requirements

### Requirement: Free text is routed to the doctor and acknowledged by template only
A message from an active, consented patient chat SHALL be stored as an event and a doctor-visible request, and answered with at most one approved template acknowledgement per person per 10 minutes. The system SHALL NOT answer its content.

#### Scenario: Normal message
- **WHEN** a bound patient sends "I travel on Friday"
- **THEN** a green request and a ContextNote event exist and the reply is the template ack without the patient's words

#### Scenario: Danger or medicine question
- **WHEN** the text has a danger word (EN or TE) or asks whether to stop or skip medicine
- **THEN** a Red (danger, plus the fast-path draft) or Amber (advice) high-priority request is created and no advice is given

#### Scenario: Repeats, unbound and stopped chats
- **WHEN** the same update id or the same words arrive again, the chat is unbound, or the patient sent /stop
- **THEN** no second request is made; unbound chats get the invitation text; after /stop nothing is stored or acked
