# ADR-013: Data Quality Anomaly Disposition and Monitoring Contract

## Status

Accepted

## Date

2026-09-01

## Context

Mercury uses explicit data contracts, Dataform assertions, and non-blocking quality models to make data-quality conditions detectable.

ADR-012 establishes the staging layer as the semantic standardization boundary between source-faithful Raw data and canonical analytical modelling. It distinguishes structural conditions that must block publication from source-quality conditions that may be preserved and surfaced without unnecessarily failing the transformation workflow.

The completed Olist staging implementation demonstrates both categories.

Blocking assertions validate conditions such as:

- required-key presence;
- declared-key uniqueness;
- semantic cast validity;
- accepted value domains;
- required formats;
- source-grain preservation.

Non-blocking quality models surface conditions such as:

- unusual order lifecycle chronology;
- missing product metadata;
- invalid or unusual physical measurements;
- payment-sequence anomalies;
- zero-value payments;
- review chronology anomalies;
- duplicate geolocation observations.

Detection alone is insufficient.

A quality model may expose an anomaly without defining:

- whether affected records remain analytically usable;
- which downstream calculations are affected;
- whether the record must be flagged, excluded, resolved, or quarantined;
- whether deterministic correction is permitted;
- when an engineer must be notified;
- who owns the response;
- how the finding is recorded historically;
- how a new anomaly is distinguished from an accepted baseline.

Some controls may report zero anomalies during initial implementation but detect anomalies in future source deliveries. Mercury must define the required response before such an event occurs.

Other controls may report known, accepted source anomalies on every execution. Repeatedly alerting engineers about an unchanged accepted baseline would create alert fatigue and weaken trust in the monitoring system.

Mercury therefore requires a platform-wide contract governing anomaly classification, disposition, historical recording, monitoring, alerting, and operational response.

This ADR defines that contract.

---

## Decision

Mercury will require every implemented data-quality control to have an explicit operational and analytical disposition.

The lifecycle of a quality finding will be:

```text
DETECT
   |
   v
RECORD
   |
   v
COMPARE WITH EXPECTED BASELINE
   |
   v
CLASSIFY AND NOTIFY
   |
   v
INVESTIGATE
   |
   v
APPLY DOCUMENTED DISPOSITION
   |
   v
RETAIN TRACEABILITY
```

Data-quality controls will be classified as either:

- **1.** blocking controls; or
- **2.** non-blocking monitors.

Every control MUST define:

- a stable control identifier;
- its control type;
- the relation or domain being evaluated;
- its severity;
- its expected baseline or threshold;
- its owner;
- its notification behavior;
- its investigation playbook;
- the permitted downstream disposition;
- the location of inspectable finding details where applicable.

Mercury MUST define behavior for a control even when its current anomaly count is zero.

---

## 1. Blocking Controls

### DQ-001 — Structural contract violations MUST block publication

A blocking control represents a condition under which the affected relation does not satisfy the minimum contract required by downstream models.

Examples MAY include:

- missing required identifiers;
- duplicate keys where uniqueness is required;
- invalid non-null semantic casts;
- violations of required source grain;
- invalid required codes or domains;
- failure to execute a required quality control.

When a blocking control fails:

- 1. the affected transformation workflow MUST fail;
- 2. affected downstream publication MUST stop;
- 3. the failure MUST be visible to the responsible engineer;
- 4. the source data and transformation logic MUST remain available for investigation;
- 5. publication MUST NOT resume until the failure is resolved or an explicit contract decision changes its classification.

A blocking failure MUST NOT be converted into a non-blocking condition merely to make a workflow succeed.

---

## 2. Non-Blocking Monitors

### DQ-002 — Analytically relevant source anomalies MAY remain non-blocking

A non-blocking monitor represents a condition that does not invalidate the structural staging contract but may affect particular downstream interpretations or calculations.

When a non-blocking anomaly is detected:

- 1. the staging workflow MAY continue;
- 2. the affected source record MUST remain traceable;
- 3. the anomaly MUST be recorded;
- 4. the applicable downstream disposition MUST be known;
- 5. notification behavior MUST follow the control's severity, threshold, and baseline;
- 6. the anomaly MUST NOT be silently ignored.

Non-blocking does not mean inconsequential.

It means that the anomaly can be governed without rejecting the entire staged relation.

---

## 3. Permitted Dispositions

### DQ-003 — Every quality finding MUST have an explicit disposition

Mercury recognizes the following disposition categories:

| Disposition | Meaning |
|---|---|
| Retain | Preserve and use the record normally. |
| Retain and flag | Preserve the record while exposing its quality condition. |
| Conditionally exclude | Exclude the record only from calculations affected by the anomaly. |
| Deterministically correct downstream | Produce a corrected downstream representation using an explicit, reproducible rule. |
| Aggregate or resolve | Convert repeated or ambiguous observations to a documented target grain. |
| Quarantine | Isolate the record from general publication while preserving it for investigation. |
| Block publication | Prevent publication because the required contract is not satisfied. |

A disposition MUST identify the scope to which it applies.

A record MAY be valid for one use and unsuitable for another.

For example, an order with invalid lifecycle chronology may remain valid for order-count analysis while being excluded from delivery-duration calculations.

Mercury MUST prefer the narrowest disposition that protects analytical correctness without unnecessarily discarding valid information.

---

## 4. Source Fidelity and Correction

### DQ-004 — Source anomalies MUST NOT be silently corrected

Raw remains the authoritative source-faithful representation.

Staging preserves source grain while standardizing representation according to ADR-012.

Mercury MUST NOT silently:

- invent missing values;
- alter timestamps to create plausible chronology;
- renumber source sequences;
- remove unexplained duplicate records;
- replace unusual values with more convenient values;
- discard structurally valid source records;
- merge semantically ambiguous observations.

A downstream correction is permitted only when:

- 1. the intended interpretation is deterministic;
- 2. the rule is documented;
- 3. the original staged value remains available;
- 4. the resulting value is traceable to the applied rule;
- 5. the correction is implemented at an appropriate downstream layer;
- 6. the correction does not misrepresent uncertainty as fact.

Where no deterministic correction exists, Mercury MUST retain, flag, conditionally exclude, aggregate, quarantine, or block according to the documented disposition.

---

## 5. Zero-Anomaly Controls

### DQ-005 — Controls reporting zero anomalies MUST still define response behavior

The absence of current findings does not remove the need for governance.

Every zero-anomaly control MUST define:

- what a future occurrence would mean;
- whether the condition is blocking or non-blocking;
- its initial severity;
- the notification threshold;
- the affected downstream uses;
- the required engineer response;
- the permitted disposition.

For a control with a validated zero baseline, the first detected occurrence SHOULD normally trigger notification unless a documented threshold establishes otherwise.

This requirement ensures that production behavior is defined before an anomaly occurs.

--- 

## 6. Historical Quality Results

### DQ-006 — Quality-control results MUST be recorded historically

Mercury's operational quality mechanism MUST persist evaluation results across executions.

At minimum, a recorded evaluation SHOULD include:

- control identifier;
- evaluated relation;
- execution or evaluation identifier;
- evaluation timestamp;
- anomaly count;
- evaluated row count where applicable;
- anomaly rate where applicable;
- expected baseline or threshold;
- resulting control status;
- severity;
- reference to inspectable finding details where applicable.

Historical results MUST make it possible to determine:

- when an anomaly first appeared;
- whether it increased or decreased;
- whether it returned to its expected state;
- whether the control itself failed to execute;
- which source delivery or transformation execution was affected.

A current-state quality view alone is not sufficient as the long-term operational record.

---

## 7. Baselines and Alerting

### DQ-007 — Non-blocking alerting MUST be baseline-aware

Mercury MUST distinguish between:

    known and accepted source condition

and:

    new or materially changed quality condition

Notification rules MAY evaluate:

- transition from zero to a positive anomaly count;
- absolute anomaly-count thresholds;
- anomaly-rate thresholds;
- changes from the previous evaluation;
- changes from an approved baseline;
- severity-specific conditions;
- failure of the monitoring control itself.

An unchanged accepted baseline SHOULD NOT generate the same actionable alert on every execution.

A material increase, unexpected new anomaly, critical threshold breach, or unknown quality state SHOULD generate notification according to the control contract.

Baseline changes MUST be reviewed and documented. Mercury MUST NOT automatically redefine an unexpected result as the new accepted baseline.

---

## 8. Severity

### DQ-008 — Every control MUST have a defined severity

Mercury will use severity to communicate potential impact and required response priority.

Initial severity classes are:

| Severity | Meaning |
|---|---|
| Informational | Known condition recorded for visibility or trend monitoring. |
| Warning | Condition may affect defined analyses and requires investigation or controlled treatment. |
| Critical | Condition threatens structural integrity, publication safety, or broad analytical correctness. |

Severity MUST reflect potential analytical or operational impact rather than anomaly count alone.

A low-count anomaly MAY be critical if it violates a required structural contract.

A high-count anomaly MAY remain informational if it is an understood source characteristic with an approved treatment.

---

## 9. Ownership and Response Playbooks

### DQ-009 — Every actionable control MUST have an owner and response playbook

An actionable quality control MUST identify the engineering role or operational owner responsible for responding to it.

The response playbook MUST define how to:

- 1. inspect the affected records;
- 2. determine whether the condition originated in the source or Mercury;
- 3. identify affected downstream relations and uses;
- 4. apply or verify the documented disposition;
- 5. escalate the issue where required;
- 6. record the investigation outcome;
- 7. approve any baseline, threshold, severity, or contract change.

Notification without ownership or an actionable response is not considered sufficient monitoring.

---

## 10. Separation of Responsibilities

### DQ-010 — Detection, persistence, evaluation, and notification MUST remain separable

Mercury separates the following responsibilities:

```text
QUALITY CONTROL
detects and exposes the condition

        |
        v

QUALITY HISTORY
records evaluations over time

        |
        v

NOTIFICATION EVALUATOR
compares results with thresholds and baselines

        |
        v

ALERTING CHANNEL
notifies the responsible engineer
```

Dataform MAY implement detection and quality-result publication.

A persistent analytical store MAY retain quality history.

A separate operational component MAY evaluate alert conditions and emit notifications.

The exact GCP implementation will be defined in an implementation design.

Dataform quality SQL MUST NOT be coupled directly to a particular email, messaging, or notification channel.

A failure of a blocking control to execute MUST block dependent publication because the required quality state is unknown.

A failure of a non-blocking monitor to execute MUST be recorded as an unknown quality state and MUST trigger notification according to its control contract.

Mercury MUST NOT interpret failure to execute a control as a zero-anomaly result.

---

## 11. Source-Specific Disposition Registers

### DQ-011 — Source-specific findings MUST be governed outside this ADR

Each implemented source domain MUST maintain a disposition register containing its concrete controls, baselines, findings, analytical effects, and response rules.

A source-specific register SHOULD include:

- control identifier;
- quality model or assertion;
- current validated baseline;
- control type;
- severity;
- affected entity or field;
- affected analytical uses;
- permitted disposition;
- notification condition;
- response playbook;
- implementation status.

Olist-specific anomaly counts and treatments will be documented in:

    [Olist anomaly disposition](../../docs/analytics/staging/olist_anomaly_disposition.md)

Source-specific findings MUST NOT redefine Mercury's platform-wide quality principles.

---

## 12. Canonical Modelling Gate

### DQ-012 — Relevant anomalies MUST have dispositions before canonical publication

Relationship exploration MAY query validated staging relations in order to discover:

- cardinalities;
- orphaned records;
- missing child records;
- join amplification;
- reconciliation gaps;
- cross-entity quality conditions.

However, a canonical model MUST NOT be considered publication-ready until:

- 1. known anomalies affecting that model have documented dispositions;
- 2. newly discovered relationship anomalies have been classified;
- 3. affected calculations follow the approved disposition;
- 4. excluded or corrected records remain traceable;
- 5. unresolved critical conditions have been addressed;
- 6. required quality flags or resolved relations have been implemented.

Relationship exploration therefore extends the quality-disposition register before canonical modelling begins.

---

## Relationship to ADR-012

ADR-012 defines the staging standard, source-level contracts, and the distinction between blocking validation and non-blocking quality surfacing.

This ADR extends that architecture by defining what Mercury must do after a quality condition has been detected.

The combined lifecycle is:

```text
RAW
preserves source evidence

        |
        v

STAGING
standardizes source representation

        |
        v

QUALITY CONTROLS
detect contract violations and source anomalies

        |
        v

ANOMALY DISPOSITION
records, classifies, monitors, and governs findings

        |
        v

RELATIONSHIP EXPLORATION
discovers cross-entity constraints and anomalies

        |
        v

CANONICAL
integrates entities using documented quality treatments
```

ADR-013 extends but does not supersede ADR-012.

---

## Consequences

### Positive

- Detected anomalies receive explicit analytical and operational treatment.
- Controls with zero current findings remain operationally meaningful.
- Known source conditions can be distinguished from new regressions.
- Engineers receive actionable notifications rather than repeated noise.
- Quality changes can be traced historically.
- Downstream exclusions and corrections remain explainable.
- Canonical models cannot silently hide unresolved quality conditions.
- Source-specific findings remain separated from platform-wide policy.
- Mercury gains a reusable quality-governance contract for future sources.

### Trade-offs

- Every quality control requires additional metadata and governance.
- Baselines and thresholds require review and maintenance.
- Historical quality persistence introduces additional storage and execution logic.
- Notification evaluation requires operational infrastructure beyond Dataform SQL.
- Engineers must maintain playbooks and ownership information.
- Some canonical models will require explicit quality flags or conditional logic.
- Initial implementation requires more work before canonical modelling begins.

These costs are accepted because detection without disposition, traceability, or response does not provide sufficient analytical reliability.

---

## Alternatives Considered

### 1. Rely only on blocking Dataform assertions

Rejected.

Not every source anomaly invalidates an entire staged relation. Treating all quality findings as blocking would unnecessarily prevent valid data from progressing.

### 2. Keep non-blocking quality views without monitoring

Rejected.

A view that is never evaluated, historically recorded, or connected to an operational response can allow new anomalies to remain unnoticed.

### 3. Alert whenever any anomaly count is greater than zero

Rejected.

Known source characteristics may legitimately remain present across executions. Repeated alerts for unchanged accepted conditions would create alert fatigue.

### 4. Automatically correct detected anomalies

Rejected.

Many source anomalies are ambiguous. Automatic correction could invent business facts, destroy source fidelity, and hide uncertainty.

### 5. Handle anomaly disposition only inside canonical SQL

Rejected.

This would scatter quality policy across downstream transformations and make treatment inconsistent, difficult to monitor, and difficult to audit.

### 6. Define responses only after an anomaly first occurs

Rejected.

This would force engineers to make analytical and operational decisions during an incident and would leave zero-result controls without an enforceable purpose.

---

## Implementation Notes

This ADR defines the platform-wide quality-governance contract rather than the complete technical monitoring implementation.

The following details will be defined separately:

- the persistent quality-results schema;
- the Dataform actions that publish quality evaluations;
- the mechanism for comparing results with baselines and thresholds;
- notification delivery channels;
- alert routing and escalation;
- execution scheduling;
- monitoring infrastructure;
- retention requirements for quality history;
- operational dashboards.

A future implementation design SHOULD document these components before monitoring infrastructure is deployed.

The Olist implementation will first record:

- 1. all existing blocking assertions;
- 2. all existing non-blocking quality controls;
- 3. their validated baselines;
- 4. their proposed severities;
- 5. their affected analytical uses;
- 6. their required dispositions;
- 7. their future notification conditions.

---

## Decision Summary

Mercury requires every data-quality control to lead to an explicit, traceable, and operationally meaningful outcome.

The governing principle is:

> Detect explicitly. Preserve evidence. Define disposition. Record history. Alert deliberately.

Blocking violations stop unsafe publication.

Non-blocking anomalies remain visible, historically traceable, and governed by documented downstream treatments.

Known baselines do not create repeated alert noise, while new or materially changed conditions require notification and investigation.

No anomaly may be silently corrected, discarded, or ignored.

This contract applies to Olist as the first implementation and to future Mercury source domains.