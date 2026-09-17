Below is a prompt series designed as a **multi-agent / staged coding-agent workflow**. Each prompt has a narrow responsibility, explicitly references the authoritative `manifest.schema.json`, and includes validation gates so later agents can build on earlier outputs without drifting from the schema.

 I recommend using **8 prompts**: schema inspection → domain extraction → relationship model → lifecycle/workflow model → policies/rules/events → manifest assembly → structural validation → semantic audit/fix.

 ## Prompt 1 — Inspect and Formalize `manifest.schema.json`

```
ROLE

You are a senior JSON Schema architect, Domain-Driven Design architect, and manifest-schema reverse-engineering specialist.

OBJECTIVE

Inspect the supplied `manifest.schema.json` and produce a precise implementation contract for a coding agent that will later generate a service manifest.

AUTHORITATIVE SOURCE

The file:

schemas/manifest.schema.json

is the ONLY authoritative source for manifest structure.

Do not infer or invent properties that are not present in this schema.

TASK

1. Read the complete manifest.schema.json.
2. Identify:
   - root-level required properties;
   - root-level optional properties;
   - entity object structure;
   - attribute object structure;
   - relationship object structure;
   - FSM/state-machine structure;
   - workflow structure;
   - workflow-step structure;
   - business-rule structure;
   - policy structure;
   - any event-related structure if one exists;
   - all enums;
   - all regex naming constraints;
   - minItems/maxItems constraints;
   - numeric constraints;
   - additionalProperties behavior;
   - default values;
   - definitions/$defs/references;
   - JSON Schema draft/version.
3. Determine exactly which primitive/type vocabulary is accepted for attributes.
4. Determine exactly which relationship cardinalities are accepted.
5. Determine whether relationship cardinality is directional according to the schema description.
6. Determine how foreign keys are represented.
7. Determine whether the schema supports:
   - cross-workflow dependencies;
   - events;
   - asynchronous execution;
   - queues;
   - workers;
   - retries;
   - policies;
   - authorization roles;
   - claims;
   - FSM guards.
8. Identify any structural ambiguity that could cause an LLM to produce semantically incorrect but schema-valid output.
9. Pay particular attention to whether N:1 relationships are supported.
10. Pay particular attention to whether a relationship from parent to child should be represented as 1:N while the child stores a foreign-key attribute.

IMPORTANT

Do not modify manifest.schema.json.

Do not generate the final manifest.

OUTPUT

Return a machine-readable analysis containing:

- ROOT_CONTRACT
- ENTITY_CONTRACT
- ATTRIBUTE_CONTRACT
- RELATIONSHIP_CONTRACT
- FSM_CONTRACT
- WORKFLOW_CONTRACT
- BUSINESS_RULE_CONTRACT
- POLICY_CONTRACT
- EVENT_CONTRACT
- NAMING_RULES
- ENUM_RULES
- TYPE_RULES
- VALIDATION_RULES
- UNSUPPORTED_CONSTRUCTS
- AMBIGUITIES_AND_HAZARDS

For every contract, identify the exact permitted property names and values from the schema.

Also provide a concise "MANIFEST_GENERATION_RULES" section containing deterministic instructions that a downstream coding agent can follow without needing to reinterpret the schema.

Do not invent any domain information.
```

---

 ## Prompt 2 — Extract the Domain Model and Explicit Requirements

```
ROLE

You are a senior Domain-Driven Design architect and learning-platform domain modeler.

OBJECTIVE

Extract the complete domain model required by the supplied learning-platform requirements without generating the final JSON manifest.

AUTHORITATIVE BUSINESS INPUTS

Use the following as authoritative business meaning:

1. System Requirements
2. Workflow Specifications
3. Policies and Business Rules
4. Business Events and Operational Events

The manifest schema remains authoritative for representation, but this task is about extracting business meaning.

DOMAIN

The platform contains these domains:

- Course Catalog
- User & Identity
- Enrollment & Execution
- Financial & Subscription
- Telemetry & Analytics Data

TASK

Build a normalized domain inventory covering all explicitly required entities.

The primary entities are:

COURSE CATALOG
- Course
- Course Version / Syllabus
- Module / Unit
- Lesson / Content Item
- Study Plan Template

USER & IDENTITY
- Student Profile
- Instructor / Educator
- User Session

ENROLLMENT & EXECUTION
- Enrollment
- Personalized Study Plan
- Lesson Completion Record

FINANCIAL & SUBSCRIPTION
- Payment Account / Customer Profile
- Subscription / Purchase Order
- Discount / Coupon

TELEMETRY & ANALYTICS
- Authentication Event Log
- Engagement Heartbeat
- Content Interaction Event
- Learning Progress Snapshot

For every entity determine:

1. Canonical entity name in PascalCase.
2. Domain.
3. Explicit purpose.
4. Attributes explicitly required by the source.
5. Attribute type implied by the source.
6. Whether the attribute is:
   - identifier;
   - foreign key;
   - lifecycle/state attribute;
   - business data;
   - metadata;
   - configuration;
   - timestamp;
   - metric.
7. Explicit uniqueness requirements.
8. Explicit nullability/optionality.
9. Explicit indexing requirements.
10. Explicit primary-key requirements.
11. Explicit state values.
12. Explicit initial state.
13. Explicit lifecycle transitions.
14. Explicit relationships to other entities.
15. Cardinality.
16. Relationship direction.
17. Workflow participation.
18. Policies applicable to the entity.
19. Business rules applicable to the entity.
20. Business/operational events associated with workflows.

CRITICAL INFERENCE RULE

Do not invent convenience fields.

Do not automatically add:

- created_at
- updated_at
- deleted_at
- version
- metadata
- status

unless explicitly required or unambiguously necessary.

If a source explicitly says an entity has a globally unique UUID identifier, model it as a UUID primary key later.

If the source names a foreign key, preserve it.

If a relationship requires a foreign-key attribute to represent the relationship, it may be inferred conservatively.

Do not create entities for:

- Kafka
- Kinesis
- Redis
- Elasticsearch
- ClickHouse
- Stripe
- PayPal
- Google
- OPA
- queues
- workers
- jobs
- caches
- search indexes
- APIs
- events

unless the manifest schema explicitly requires them as domain entities.

OUTPUT

Produce a normalized domain inventory.

For each entity provide:

ENTITY
- canonical_name
- domain
- purpose
- attributes
- relationships
- states
- workflows
- policies
- business_rules
- events

Then produce:

GLOBAL_RELATIONSHIP_MATRIX

For every relationship explicitly identify:

source
target
semantic_cardinality
direction
foreign_key_attribute
justification

Do NOT generate the final manifest.
```

---

 ## Prompt 3 — Build the Relationship and Aggregate Model

```
ROLE

You are a senior DDD aggregate-design specialist and relational/domain relationship modeling expert.

OBJECTIVE

Using the extracted learning-platform domain requirements, construct the exact relationship model that can safely be represented by manifest.schema.json.

AUTHORITATIVE INPUTS

- schemas/manifest.schema.json
- the supplied System Requirements
- the supplied Workflow Specifications
- the supplied Policies and Business Rules

CRITICAL CARDINALITY RULE

The manifest relationship vocabulary supports:

- 1:1
- 1:N
- N:M

It does NOT support N:1.

Relationship cardinality is directional from source to target.

Therefore:

Course -> CourseVersion = 1:N

NOT:

CourseVersion -> Course = 1:1

Likewise:

CourseVersion -> Module = 1:N
Module -> Lesson = 1:N
CourseVersion -> StudyPlanTemplate = 1:N

Child foreign keys may be represented as ordinary attributes:

CourseVersion.course_id
Module.course_version_id
Lesson.module_id
StudyPlanTemplate.course_version_id

Do NOT create reverse N:1 relationships.

TASK

Analyze all domain relationships and produce the canonical relationship graph.

For every candidate relationship:

1. Determine actual business cardinality.
2. Determine aggregate/parent ownership.
3. Determine source-to-target direction.
4. Determine whether the direction is representable.
5. If parent-to-many-child, model as 1:N.
6. Determine the child foreign key if explicitly required or conservatively necessary.
7. Do not convert N:1 into 1:1.
8. Do not create an intermediary entity merely because N:1 is unsupported.
9. Use N:M only where the business meaning is genuinely many-to-many.
10. Use 1:1 only where each source can have at most one target and each target belongs to at most one source.

Explicit relationships to investigate include, at minimum:

Course -> CourseVersion
CourseVersion -> Module
Module -> Lesson
CourseVersion -> StudyPlanTemplate
StudentProfile -> UserSession
StudentProfile -> Enrollment
Instructor -> Course
Instructor -> CourseVersion where explicitly justified
Enrollment -> PersonalizedStudyPlan
Enrollment -> LessonCompletionRecord
StudentProfile -> PaymentAccount
PaymentAccount -> PaymentMethod if payment-method representation is supported by the source/schema
StudentProfile -> PurchaseOrder
PurchaseOrder -> Discount/Coupon where applicable
StudentProfile -> AuthenticationEventLog
UserSession -> AuthenticationEventLog
Enrollment -> ContentInteractionEvent
Lesson -> ContentInteractionEvent
CourseVersion -> LearningProgressSnapshot where applicable
StudentProfile -> LearningProgressSnapshot

Do not assume every listed relationship must exist. Only model relationships justified by the source and supported by the schema.

Also distinguish:

- domain relationship;
- foreign-key attribute;
- aggregate boundary;
- workflow dependency.

Do not confuse these.

OUTPUT

Return:

1. CANONICAL_RELATIONSHIP_GRAPH
2. FOREIGN_KEY_REQUIREMENTS
3. RELATIONSHIPS_REJECTED_AND_WHY
4. AGGREGATE_BOUNDARIES
5. CARDINALITY_VALIDATION

For each canonical relationship provide:

source
target
cardinality
foreign_key_on_source_if_any
business_justification

The output is an intermediate design artifact, not the final manifest.
```

---

 ## Prompt 4 — Model FSMs, Workflows, and Dependencies

```
ROLE

You are a senior workflow-modeling specialist, DDD lifecycle architect, and state-machine designer.

OBJECTIVE

Translate the supplied workflows into deterministic manifest-compatible FSMs and workflows.

AUTHORITATIVE INPUTS

- schemas/manifest.schema.json
- supplied workflow specifications
- supplied policies and business rules

TASK

For every entity, identify only explicitly supported lifecycle states and transitions.

Create an FSM only when the source explicitly establishes stateful behavior.

An FSM requires:

- state_attribute
- initial_state
- states
- transitions

Do not create an FSM merely because an entity participates in a workflow.

DO NOT INVENT STATES.

Examples explicitly present in the source include:

Course:
- DRAFT
- AVAILABLE
- WITHDRAWN

Course Version:
- IN_DEVELOPMENT
- ACTIVE
- DEPRECATED

Lesson:
- READY
- PROCESSING
- FAILED only if explicitly required by the workflow/business rules and supported by the source

Enrollment:
- ACTIVE
- SUSPENDED
- COMPLETED
- CANCELED

Purchase Order / Subscription:
- PENDING
- PAID
- PAST_DUE
- CANCELED
- REFUNDED
- PARTIALLY_REFUNDED where explicitly applicable

Study Plan Template:
- PUBLISHED where the source establishes it as a lifecycle state and the schema supports FSM modeling

Do not automatically convert every event or processing phase into an FSM.

For every transition:

- trigger
- source_state
- target_state
- guards only where the source explicitly defines transition preconditions

Examples of legitimate guards:

Course AVAILABLE:
requires at least one active Course Version
requires valid registration window

Course Version ACTIVE:
requires valid modules and lessons
requires processed assets

Enrollment COMPLETED:
requires 100% required curriculum completion

Do not turn generic workflow steps into guards.

WORKFLOW MODELING

Create one Workflow for every independently identifiable business workflow.

Required workflows include:

Course:
- Course Creation & Metadata Drafting
- Course Publishing & Availability
- Course Withdrawal

Course Version:
- Version Versioning & Drafting
- Syllabus Freeze & Activation

Module:
- Module Reordering & Structuring

Lesson:
- Content Ingestion & Processing

Study Plan Template:
- Pacing Profile Generation

Student Profile:
- Google SSO Registration & Onboarding
- Profile & Preferences Management
- Account Anonymization / Deactivation

Instructor:
- Instructor Provisioning & Access Control
- Course Assignment & Governance

User Session:
- Session Initialization & Token Issuance
- Session Validation & Activity Renewal
- Session Termination & Revocation

Enrollment:
- Enrollment Provisioning & Activation
- Lifecycle Status Transition

Personalized Study Plan:
- Study Plan Instantiation & Schedule Generation
- Schedule Adjustment & Recalculation

Lesson Completion Record:
- Progress Tracking & Evaluation
- Prerequisite Validation & Unlocking

Payment Account:
- Gateway Account Provisioning
- Payment Method Management

Discount:
- Coupon Validation & Application
- Usage Tracking & Exhaustion

Purchase Order:
- Checkout & One-Time / Recurring Order Processing
- Subscription Lifecycle Management
- Refund & Cancellation Execution

Authentication Event Log:
- Audit Log Ingestion & Security Indexing

Engagement Heartbeat:
- High-Frequency Ping Processing

Content Interaction Event:
- Media & Interaction Telemetry Tracking

Learning Progress Snapshot:
- Snapshot Calculation & Metric Aggregation

WORKFLOW STEPS

Each step must:

- have a unique snake_case name;
- contain a semantic action;
- use depends_on only for genuine execution dependencies.

Do not serialize independent operations unnecessarily.

Do not use depends_on to represent asynchronous completion.

For asynchronous processing, preserve semantics in action text, e.g.:

"mark_lesson_ready_after_successful_media_processing_and_update_duration"

not:

"depends_on": ["media_worker"]

because workers are not workflow entities.

MAX_RETRIES

Only specify max_retries when the source explicitly gives retry behavior.

Examples:

Subscription dunning:
3 retry attempts over 7 days.

Do not invent retry values elsewhere.

OUTPUT

Produce:

1. FSM_MODEL
2. WORKFLOW_MODEL
3. WORKFLOW_DEPENDENCIES
4. TRANSITION_GUARDS
5. RETRY_CONFIGURATION

Do not produce the final JSON manifest.
```

---

 ## Prompt 5 — Model Policies, Business Rules, and Events

```
ROLE

You are a senior domain-policy architect, business-rule modeler, and event semantics specialist.

OBJECTIVE

Extract and normalize all policies, business rules, business events, and operational events from the supplied learning-platform specification so they can later be represented in manifest.schema.json.

AUTHORITATIVE INPUTS

Use the supplied Policies and Business Rules and Business/Operational Events as authoritative.

Do not invent rules merely because they seem useful.

POLICIES

Create policies only where the source explicitly identifies:

- authorization;
- actor restrictions;
- roles;
- permissions;
- security requirements;
- compliance requirements;
- access-control requirements.

Do not infer a role merely because an entity exists.

For example:

Instructor entity != automatically an "instructor" authorization role.

Use authorization roles only where explicitly established.

BUSINESS RULES

Use business rules for:

- reusable domain invariants;
- eligibility conditions;
- validation constraints;
- state-independent business constraints;
- integrity requirements.

Do not duplicate constraints that are fully represented structurally.

Examples:

- primary key -> structural attribute constraint
- unique slug -> unique attribute
- nullable -> nullable attribute

A business rule is appropriate when the source expresses a reusable business invariant.

Each business rule must eventually have:

- name
- target_entity
- expression
- error_message

Expressions must be deterministic and non-empty.

EVENTS

The source includes Business Events and Operational Events.

The manifest schema may or may not have an event construct.

If the manifest schema does NOT support event objects:

- do not create event entities;
- do not invent event schema properties;
- preserve event semantics inside appropriate workflow actions.

Examples:

"emit_course_published_event_to_update_search_indices_and_catalog_caches"

"emit_payment_settled_event_to_trigger_enrollment_provisioning"

"emit_learning_progress_snapshot_updated_event_after_successful_persistence"

Do not create:

Event
KafkaTopic
EventConsumer
EventHandler
Queue
Worker

as domain entities.

TASK

Normalize all explicit policies and business rules for:

Course
CourseVersion
Module
Lesson
StudyPlanTemplate
StudentProfile
Instructor
UserSession
Enrollment
PersonalizedStudyPlan
LessonCompletionRecord
PaymentAccount
Discount/Coupon
PurchaseOrder/Subscription
AuthenticationEventLog
EngagementHeartbeat
ContentInteractionEvent
LearningProgressSnapshot

Also normalize all events by:

- entity
- workflow
- business vs operational
- trigger
- intended semantic effect

Ensure event names are preserved faithfully when they can be represented.

OUTPUT

Return:

1. POLICY_CATALOG
2. BUSINESS_RULE_CATALOG
3. EVENT_CATALOG
4. AUTHORIZATION_MODEL
5. UNSUPPORTED_EVENT_REPRESENTATION

Do not generate the final manifest.
```

---

 ## Prompt 6 — Assemble the Complete Manifest

```
ROLE

You are a senior backend architect, DDD modeler, workflow specialist, and JSON Schema implementation expert.

OBJECTIVE

Generate exactly one implementation-ready JSON service manifest conforming strictly to schemas/manifest.schema.json.

AUTHORITATIVE INPUTS

1. schemas/manifest.schema.json
   - authoritative for structure.
2. Supplied system requirements
   - authoritative for domain meaning.
3. Supplied workflows
   - authoritative for business processes.
4. Supplied policies/business rules
   - authoritative for domain constraints.
5. Intermediate artifacts produced by the preceding modeling agents
   - use these as normalized interpretations, but re-check them against the original source.

PRIMARY OBJECTIVE ORDER

1. Structural validity against manifest.schema.json.
2. Semantic correctness.
3. Preservation of explicit business intent.
4. Deterministic modeling.
5. Minimal inference.
6. No invented concepts.

OUTPUT REQUIREMENT

Return ONLY ONE JSON OBJECT.

No Markdown.
No code fences.
No explanation.
No comments.
No validation report.

The response must begin with { and end with }.

ENTITY RULES

Create only explicitly justified domain entities.

Use canonical PascalCase names.

Every entity must have attributes.

Do not create infrastructure entities.

Do not invent convenience fields.

ATTRIBUTES

Only create an attribute when:

1. explicitly named by the source;
2. provided by an attached domain schema;
3. unavoidable to represent an explicit domain requirement;
4. conservatively required as a foreign key for an explicit relationship.

Use only manifest-supported types.

If supported types are:

str
int
float
bool
datetime
uuid
dict
list

use only those values.

Use uuid primary keys where the source explicitly establishes UUID/global uniqueness.

RELATIONSHIPS

Use only:

1:1
1:N
N:M

Cardinality is directional.

Never convert N:1 into 1:1.

For example:

Course -> CourseVersion = 1:N

CourseVersion -> Module = 1:N

Module -> Lesson = 1:N

CourseVersion -> StudyPlanTemplate = 1:N

Child foreign keys remain attributes:

CourseVersion.course_id
Module.course_version_id
Lesson.module_id
StudyPlanTemplate.course_version_id

Do not create reverse relationships.

FSM

Use FSM only for explicit lifecycle behavior.

Every FSM must reference a real state attribute.

Every initial_state must exist in states.

Every transition must have:

trigger
source_state
target_state

Only use explicit transition guards.

WORKFLOWS

Create every explicitly identified business workflow.

Every workflow must have steps.

Every step must have:

name
action

Step names must be concise snake_case.

Use depends_on only for actual same-workflow execution dependencies.

Do not create cross-workflow dependency references.

Do not use dependencies to represent asynchronous completion.

Preserve async behavior inside actions.

BUSINESS RULES

Represent reusable domain invariants.

Do not duplicate structural constraints unnecessarily.

POLICIES

Represent explicit authorization/security/compliance policies only.

Do not invent roles or claims.

EVENTS

If events are unsupported structurally, preserve them in workflow actions.

Never create infrastructure entities for events.

RETRIES

Only include max_retries where explicitly specified.

SELF-CHECK BEFORE OUTPUT

Verify:

1. Every entity is justified.
2. Every attribute is justified.
3. No speculative entities exist.
4. No speculative attributes exist.
5. Every relationship target exists.
6. Every relationship direction is correct.
7. No N:1 relationship has been converted to 1:1.
8. Child foreign keys are represented as attributes where appropriate.
9. Every FSM state attribute exists.
10. Every FSM initial state exists.
11. Every transition is explicitly justified.
12. Every guard is a real transition precondition.
13. Every workflow has steps.
14. Step dependencies are intra-workflow.
15. Dependency graphs are acyclic.
16. Async completion is not falsely represented through depends_on.
17. Every business-rule target entity exists.
18. Every policy role is explicitly supported.
19. No infrastructure entity exists.
20. No unsupported schema property exists.
21. No additional properties exist.
22. All enum values are legal.
23. All names satisfy schema patterns.
24. Required arrays are non-empty.
25. Required properties are present.
26. No duplicate semantic facts are unnecessarily represented.
27. FSM and workflow behavior are consistent.
28. Relationships and foreign keys are consistent.
29. Events are not incorrectly modeled as entities.
30. The complete JSON validates against manifest.schema.json.

Generate the final JSON only after all checks pass.
```

---

 ## Prompt 7 — Structural Validation and Automatic Repair

```
ROLE

You are a JSON Schema validation engineer and manifest repair specialist.

OBJECTIVE

Validate the generated service manifest against:

schemas/manifest.schema.json

Do not redesign the domain unless required to make the manifest conform to the schema and preserve the supplied business meaning.

INPUT

- schemas/manifest.schema.json
- generated manifest from the previous agent

TASK

Perform a strict JSON Schema Draft 2020-12 validation.

Check:

ROOT
- root object;
- required properties;
- version format;
- service_name format;
- additionalProperties.

ENTITIES
- required entity properties;
- entity naming;
- attributes;
- attribute naming;
- supported types;
- primary_key constraints;
- unique constraints;
- nullable constraints;
- index constraints.

RELATIONSHIPS
- required properties;
- valid target_entity;
- legal cardinality;
- valid foreign_key references;
- no unsupported N:1 representation;
- no references to nonexistent entities.

FSM
- state_attribute exists;
- initial_state exists;
- state list is valid;
- transitions reference existing states;
- transition schema is valid;
- guards conform to the schema.

WORKFLOWS
- workflow names;
- required steps;
- unique step names;
- valid dependency references;
- dependency constraints;
- max_retries constraints.

BUSINESS RULES
- required fields;
- valid target_entity;
- non-empty expression;
- non-empty error_message.

POLICIES
- valid roles;
- valid actions;
- valid claims if supported;
- no unsupported fields.

TASK 2

If the manifest is invalid:

1. Identify every structural validation error.
2. Repair only what is necessary.
3. Do not invent new domain concepts.
4. Do not weaken constraints simply to pass validation.
5. Do not remove explicit business meaning unless the schema cannot represent it.
6. When information cannot be represented structurally, preserve it using an existing supported free-form field such as action or expression where semantically appropriate.
7. Revalidate after each repair.

TASK 3

Perform a schema-property audit.

For every object in the manifest verify that every property is explicitly allowed by manifest.schema.json.

TASK 4

Perform a reference audit.

Every:

- target_entity
- foreign_key
- state_attribute
- dependency reference
- rule target

must point to an existing valid construct.

OUTPUT

If valid, return the complete corrected manifest only.

If invalid after all conservative repairs, return the complete best-effort corrected manifest only.

Never return commentary, Markdown, validation explanations, or a separate report.
```

---

 ## Prompt 8 — Final Semantic Audit and Manifest Hardening

```
ROLE

You are the final principal architect responsible for approving an implementation-ready domain service manifest.

OBJECTIVE

Perform a final semantic audit of the generated manifest against the original learning-platform requirements and manifest.schema.json.

INPUTS

- schemas/manifest.schema.json
- original system requirements
- original workflow specifications
- original policies/business rules
- original business/operational events
- generated manifest

IMPORTANT

Do not merely check whether the JSON is syntactically valid.

The manifest must be both:

1. structurally valid;
2. semantically faithful.

AUDIT 1 — ENTITY COMPLETENESS

Verify all explicitly required entities are represented where the manifest schema permits them:

Course
CourseVersion
Module
Lesson
StudyPlanTemplate
StudentProfile
Instructor
UserSession
Enrollment
PersonalizedStudyPlan
LessonCompletionRecord
PaymentAccount
PurchaseOrder/Subscription
Discount/Coupon
AuthenticationEventLog
EngagementHeartbeat
ContentInteractionEvent
LearningProgressSnapshot

Do not add entities merely because they appear in implementation descriptions.

AUDIT 2 — ATTRIBUTE COMPLETENESS

Verify explicitly required attributes are represented.

Do not add speculative attributes.

Pay special attention to:

- IDs
- foreign keys
- state fields
- timestamps
- pricing
- registration windows
- sequence order
- lesson duration
- pacing offsets
- Google identity fields
- session/security metadata
- payment gateway identifiers
- coupon constraints
- order state
- telemetry context
- learning metrics

Only include fields actually supported by the source and manifest schema.

AUDIT 3 — RELATIONSHIP CORRECTNESS

This is the highest-risk audit.

For every relationship ask:

1. What is the real business cardinality?
2. Is the source direction parent -> child?
3. Is the relationship represented directionally?
4. Has N:1 accidentally become 1:1?

Expected examples:

Course -> CourseVersion = 1:N
CourseVersion -> Module = 1:N
Module -> Lesson = 1:N
CourseVersion -> StudyPlanTemplate = 1:N

If a child has:

course_id
course_version_id
module_id
enrollment_id
student_profile_id

do not automatically create reverse 1:1 relationships.

AUDIT 4 — FSM CONSISTENCY

Verify:

Course:
DRAFT -> AVAILABLE
AVAILABLE -> WITHDRAWN

Course Version:
IN_DEVELOPMENT -> ACTIVE
ACTIVE -> DEPRECATED

Enrollment:
ACTIVE -> SUSPENDED
ACTIVE -> CANCELED
ACTIVE -> COMPLETED
SUSPENDED -> ACTIVE

Purchase Order / Subscription:
only include explicitly supported transitions.

Do not invent lifecycle states.

Verify every workflow state transition exists in the FSM and every FSM transition is justified by the source.

AUDIT 5 — WORKFLOW COMPLETENESS

Verify every explicit workflow exists.

Verify every workflow has semantically meaningful steps.

Verify dependencies only represent execution prerequisites.

Do not turn every numbered list item into an artificial dependency if the operations are independent.

Do not use depends_on to represent:

- Kafka;
- queues;
- worker completion;
- webhook waiting;
- asynchronous callbacks.

Preserve such behavior inside actions.

AUDIT 6 — BUSINESS RULES

Verify explicit reusable rules such as:

- slug uniqueness;
- pricing bounds;
- active-version requirement;
- registration-window validity;
- module sequence integrity;
- DAG prerequisite constraint;
- content readiness;
- curriculum coverage;
- timezone validity;
- session concurrency;
- token lifetime;
- enrollment version locking;
- completion thresholds;
- coupon expiry/redemption;
- order state transitions;
- dunning limits;
- refund windows;
- telemetry rate limits;
- interaction deduplication;
- progress calculation;
- learning streak requirements.

Do not duplicate structural constraints unnecessarily.

AUDIT 7 — POLICIES

Verify explicitly stated policies including relevant:

- authorization;
- OAuth trust;
- privacy;
- PCI;
- access control;
- audit immutability;
- telemetry retention;
- enrollment context;
- dashboard freshness.

Do not invent authorization roles.

AUDIT 8 — EVENTS

Verify all meaningful source events are preserved.

If the manifest schema does not support events:

- do not create event entities;
- do not create event infrastructure;
- preserve event semantics in workflow actions.

AUDIT 9 — ASYNC PROCESSING

Verify asynchronous behavior remains semantically correct.

Example:

Correct:
trigger_media_processing
then action describing READY only after successful processing.

Incorrect:
depends_on a nonexistent media-worker entity.

AUDIT 10 — NO SPECULATION

Search the manifest for invented:

- entities;
- attributes;
- states;
- transitions;
- guards;
- roles;
- claims;
- retry counts;
- infrastructure;
- queues;
- workers;
- events as entities;
- unsupported relationships.

Remove speculative constructs unless directly justified.

AUDIT 11 — INFORMATION LOSS

For every source requirement that cannot be represented directly by manifest.schema.json, determine whether its meaning is preserved in:

- attribute;
- relationship;
- FSM;
- business rule;
- workflow dependency;
- workflow action;
- policy.

Do not silently discard explicit business requirements when an appropriate supported representation exists.

FINAL VALIDATION

Perform both:

A. JSON Schema validation
B. Semantic domain validation

Then repair any discovered issue conservatively.

FINAL OUTPUT

Return ONLY the final corrected JSON manifest.

No Markdown.
No code fence.
No explanation.
No audit report.
No warnings.
No comments.
No alternative.

The output must begin with { and end with }.
```

 ## Recommended agent execution order

 Use the prompts in this sequence:

 1. **Schema Inspector** → establishes exactly what the manifest can represent.
2. **Domain Extractor** → establishes the canonical entity/attribute inventory.
3. **Relationship Architect** → prevents the particularly dangerous `N:1 → 1:1` modeling error.
4. **Workflow/FSM Architect** → models lifecycle and workflow semantics.
5. **Policy/Rules Architect** → separates invariants, policies, and events.
6. **Manifest Generator** → assembles the actual JSON.
7. **Schema Validator/Repair Agent** → fixes structural violations.
8. **Principal Architect Audit** → performs the final semantic hardening.

 For the actual coding-agent pipeline, I would make **Prompt 6 the only agent allowed to create the production manifest initially**, and make Prompts 7–8 **read/validate/repair agents**. That separation substantially reduces the risk that a validation agent starts inventing domain concepts while trying to fix a structural problem.
