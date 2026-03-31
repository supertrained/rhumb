# Resolve Capability Composition — Expert Panel Analysis

**Date:** 2026-03-30  
**Convened by:** Pedro, Rhumb Operator  
**Subject:** Whether Rhumb Resolve should remain a managed execution / control plane or move up-stack into capability and outcome delivery via deterministic and multi-step composition  
**Classification:** Internal Strategic — Board-level decision input

---

## Table of Contents

1. [Executive Verdict](#executive-verdict)
2. [Definitions: Three Layers and Three Kinds of Abstraction](#definitions-three-layers-and-three-kinds-of-abstraction)
3. [Panel 1: Infrastructure / Product / Platform Operators](#panel-1-infrastructure--product--platform-operators)
4. [Panel 2: Agent UX / Systems / Strategy Thinkers](#panel-2-agent-ux--systems--strategy-thinkers)
5. [Panel 3: Adversarial / Red Team / Reliability / Neutrality](#panel-3-adversarial--red-team--reliability--neutrality)
6. [Synthesis: Direct Answers](#synthesis-direct-answers)
7. [Framework: Raw Access vs Single Capability vs Composed Capability](#framework-raw-access-vs-single-capability-vs-composed-capability)
8. [Which Categories Are Good Candidates for Composition vs Bad Candidates](#which-categories-are-good-candidates-for-composition-vs-bad-candidates)
9. [Where Composition Should Live: Agent, Rhumb, or Hybrid](#where-composition-should-live-agent-rhumb-or-hybrid)
10. [Neutrality, Trust, and Provider Relationships](#neutrality-trust-and-provider-relationships)
11. [Economics and Margin Potential](#economics-and-margin-potential)
12. [What Resolve Should Be NOW vs LATER vs NEVER](#what-resolve-should-be-now-vs-later-vs-never)
13. [Recommended Product Posture in Plain English](#recommended-product-posture-in-plain-english)
14. [90-Day Implications if the Thesis Is True](#90-day-implications-if-the-thesis-is-true)
15. [Appendix A: Minority Views That Need to Stay Alive](#appendix-a-minority-views-that-need-to-stay-alive)
16. [Appendix B: Decision Tests for Every Proposed Composed Capability](#appendix-b-decision-tests-for-every-proposed-composed-capability)
17. [Appendix C: Risk Registry](#appendix-c-risk-registry)
18. [Final Assessment](#final-assessment)

---

## Executive Verdict

### Direct answer: **Do agents actually want this?**

**Yes, but only in a very specific shape.** Agents do **not** broadly want a black-box “outcome engine” hiding arbitrary workflows behind innocent verbs. They **do** want:

1. **Raw provider/tool access** when they need precision, custom logic, or debuggability.
2. **Single capability delivery** when they want the platform to normalize a messy category into a stable verb.
3. **A narrow set of explicit, inspectable, deterministic composed capabilities** for repetitive plumbing where the agent cares about the outcome and not the exact internal sequence.

The strongest answer from the panel was not “agents want outcomes” or “agents want primitives.” It was:

**Agents want progressive abstraction with escape hatches.**

That means Resolve should let an agent say:
- “Use provider X directly”
- “Give me `email.send` regardless of provider”
- “Run `prospect.find_and_enrich` and show me exactly what happened”

What agents do **not** want is:
- silent provider switching with no trace,
- hidden multi-step orchestration on irreversible actions,
- mystery failures where the API contract says “send email” but the platform actually did seven things first and any one of them could have broken.

### Direct answer: **Is this a better business than pure managed execution?**

**Potentially yes, but only as a selective layer on top of managed execution — not as a replacement for it.**

Pure managed execution is a thinner business, but it is cleaner, more neutral, more legible, and operationally safer. Composition can improve margins, stickiness, and perceived product value **if** Rhumb stays disciplined and productizes only the narrow band where it has repeatable advantage.

The business answer from the panel was:

- **Managed execution alone** = credible substrate, lower trust risk, thinner margins, easier provider relations.
- **Single capability delivery** = the best near-term wedge; this is where product value and operational sanity intersect.
- **Composed multi-step delivery** = higher upside but only when deterministic, common, auditable, and low-liability.
- **Open-ended outcome execution** = seductive, demo-friendly, margin-illusory, support-heavy, neutrality-damaging, and likely the wrong product for Resolve.

So the honest answer is:

**The better business is not “composition instead of managed execution.” It is “managed execution as substrate, single capability delivery as default product, and a small catalog of explicit deterministic compositions as the premium layer.”**

### Core recommendation in one sentence

**Resolve should become the trusted execution substrate for agents, with capability-level APIs as the main surface and a very selective set of traceable deterministic compositions — but it should not become a hidden open-ended workflow engine masquerading as a neutral control plane.**

---

## Definitions: Three Layers and Three Kinds of Abstraction

Before the panel, we forced a vocabulary split because too much of this debate collapses very different things into one vague phrase: “higher-level capabilities.” That vagueness is dangerous.

### The three product layers

#### 1. Raw provider / tool access
The agent asks for a provider or tool directly.

Examples:
- `provider=brave-search-api`
- `provider=google-ai`
- `provider=apollo`
- `provider=firecrawl`

Promise:
- “You get close-to-provider semantics, explicit provider choice, explicit knobs.”

Best for:
- power users,
- precise control,
- debugging,
- agents that already know what they want.

#### 2. Single capability delivery
The agent asks for a normalized capability that can be fulfilled by one provider.

Examples:
- `search.query`
- `email.send`
- `person.enrich`
- `document.parse`
- `page.capture_screenshot`

Promise:
- “You ask for the job category; Resolve selects and normalizes the provider.”

Best for:
- agent developers who want a stable contract,
- faster integration,
- less provider-specific code.

#### 3. Composed / multi-step capability delivery
The agent asks for a higher-order capability that may require multiple steps or providers.

Examples:
- `prospect.find_and_enrich`
- `company.research_brief`
- `page.monitor_and_notify`
- `lead.capture_score_route`

Promise:
- “You ask for the business outcome at a higher level; Resolve may orchestrate multiple deterministic steps underneath.”

Best for:
- repetitive workflows,
- common business tasks with standard shape,
- cases where the hidden plumbing is commodity but the outcome is stable.

### The three kinds of abstraction that people wrongly mix together

#### A. Policy / routing abstraction
Same capability, same general semantics, different provider chosen under the hood.

Example:
- `search.query` routes to Brave, Tavily, or Exa depending on cost / freshness / availability / user pinning.

This is **not** composition in the scary sense. It is mostly control-plane logic.

#### B. Deterministic composition
A declared sequence or graph of steps is used to fulfill a higher-order capability.

Example:
- `prospect.find_and_enrich` = search company domain → identify likely contact → enrich person → verify email → return ranked candidates.

This can be safe **if** the steps are explicit, bounded, and auditable.

#### C. Agentic open-ended workflow
The platform itself plans, branches, retries, adapts, and potentially changes tactics dynamically in pursuit of an underspecified outcome.

Example:
- “Research this company and find me the best contact and draft the outreach email” where the system may crawl multiple sources, infer intent, evaluate quality, and choose actions without a declared plan.

This is **not** just a higher-level capability. It is effectively another agent. It has different trust, liability, and debuggability properties.

### The most important conceptual separation

The panel was nearly unanimous on this:

**Policy abstraction, deterministic composition, and agentic open-ended workflows are not the same product.**

If Resolve treats them as the same thing, it will build the wrong abstractions, misprice risk, and confuse users.

---

## Panel 1: Infrastructure / Product / Platform Operators

### Panelists

1. **Maya Srinivasan** — ex-Stripe platform PM, built capability-normalization layers for payment rails  
2. **Ethan Cole** — API gateway architect, ex-Kong / Apigee  
3. **Natalie Romero** — ex-Zapier product leader, workflow platform operator  
4. **Benji Park** — managed services GM, ran enterprise integrations for communications APIs  
5. **Rina Patel** — developer platform operator, built internal execution planes for multi-tenant SaaS  
6. **Jonas Meyer** — CTO of a B2B integration startup acquired by a CRM vendor  
7. **Helena Xu** — SRE leader, ran reliability for a high-volume orchestration platform  
8. **Owen Foster** — ex-Segment product strategist, abstraction-layer specialist  
9. **Carla Mendes** — marketplace operations lead, managed provider onboarding and rev-share contracts  
10. **Victor Anselm** — enterprise workflow product operator, ex-Workato  
11. **Priya Raman** — billing and packaging specialist for usage-based infrastructure  
12. **Samir Haddad** — infrastructure finance operator, built margin models for API-backed SaaS

---

### Session Transcript: Does capability / outcome delivery create real value, and where does it break?

**Moderator:** Rhumb Resolve can stay a managed execution plane — providers, credentials, billing, trust, routing. Or it can move up a layer and let agents ask for what they want done, not which provider to call. Is that real product value or abstraction theater?

**Maya Srinivasan:** It is real value **at the single capability layer**. That’s the cleanest answer. When developers ask for `card.charge`, `person.enrich`, `document.parse`, or `search.query`, they are telling you the market already wants one layer of abstraction above the vendor. The value is: normalized input, normalized errors, normalized billing, and sane defaults.

Where teams get into trouble is when they take that success and assume the next move is “therefore the platform should also own the entire workflow.” That’s not a law of nature. Often it’s where the product gets mushy.

**Ethan Cole:** I agree with Maya. There are three escalating promises here:

1. “We will route your request.”
2. “We will normalize the category.”
3. “We will achieve your business outcome.”

Each jump multiplies operational burden.

The first one is mainly control plane. The second one is product and schema design. The third one is you implicitly accepting responsibility for planning, state transitions, partial failures, and sometimes business judgment. That third promise is much more expensive than most founders think.

**Natalie Romero:** From workflow platforms, here’s the learned scar tissue: users say they want outcomes, but what they usually mean is “I don’t want to rebuild boring glue.” Those are not the same thing. If you interpret “I want the outcome” too literally, you end up owning edge cases you should not own.

A user saying “send an email” probably means one of three things:
- “just hit the provider API,”
- “abstract provider choice and auth,” or
- “research the recipient, personalize the draft, check unsubscribe status, choose send time, and then send.”

Those are three totally different products with different liability.

**Benji Park:** Managed services companies learn this brutally. The higher-level the promise, the more every bad result becomes a support ticket, even when every individual step technically succeeded. The sentence “but the workflow completed” is meaningless when the user’s expectation was “I wanted the right person emailed with the right message.”

That’s why I’m pro-composition only when the expected outcome can be objectively tested. If the success state is subjective, ambiguous, or business-context dependent, the composition should stay with the agent, not the platform.

**Rina Patel:** I’d frame the boundary this way: the platform should own **reliable execution of commodity subproblems**. The agent should own **task strategy and context-specific reasoning**.

Platform-owned:
- auth,
- billing,
- provider routing,
- retries,
- normalization,
- deterministic joins across boring steps,
- audit trails.

Agent-owned:
- whether the task should happen,
- why it matters,
- tradeoffs between speed/cost/quality,
- interpreting ambiguous business instructions,
- deciding whether a result is acceptable.

**Jonas Meyer:** This is where many infrastructure companies accidentally become bad workflow companies. They think composition adds value because it looks closer to the user’s job-to-be-done. But the minute the job involves ambiguity, you are no longer just composing APIs. You are operating a business process. That means support, SLAs, exception queues, human review, and endless “why did it do that?” tickets.

**Helena Xu:** Reliability math gets worse fast under composition. A single provider call already has latency variance, quota issues, partial outages, schema drift, and weird edge cases. Now string together four steps across three vendors. Even if each step is 99% reliable, your end-to-end success rate is worse than people intuit.

And that’s before you account for semantic failure — cases where the workflow technically returns a result but the result is wrong, stale, or useless.

**Moderator:** So is composition a trap?

**Helena Xu:** No. It’s a trap **when hidden** and **when under-observed**. Deterministic composition can be excellent product value when you have:
- clear state transitions,
- bounded steps,
- stable inputs/outputs,
- a transparent trace,
- good fallbacks,
- obvious partial-failure handling.

A page monitor that snapshots a page, extracts key fields, diffs them, and notifies on change? Great candidate. A “research this company” endpoint that fans out across web search, website crawl, extraction, confidence ranking, and summarization? Possibly useful, but only if you expose provenance and confidence.

**Owen Foster:** Segment is a helpful analogy. Segment won because it normalized events and destinations, not because it promised “we will make your GTM motion work.” Resolve can win by normalizing execution and capabilities. It should be very careful before claiming ownership of business outcomes.

The stable middle layer is usually the money layer.

**Carla Mendes:** Provider relations change when you move from “we route requests” to “we synthesize outcomes.” Providers are often comfortable with aggregation. They are less comfortable with intermediaries that swallow attribution, hide which vendor was used, or commoditize them into invisible ingredients.

If Rhumb wants to preserve neutrality and good provider relations, it should assume providers will ask:
- When are you choosing me?
- When are you not?
- Are you showing the customer that I was used?
- Are you learning from my output to replace me?
- Are you biasing routes toward whoever pays you more?

These questions get sharper under composition.

**Victor Anselm:** The operational line I’d draw is simple: if the workflow has branching based on business semantics rather than infrastructure semantics, the agent probably needs to stay in the loop.

Good platform branching:
- provider A timed out → fallback to provider B,
- schema missing field → run validator,
- dedupe found two identical records → merge.

Dangerous platform branching:
- “this looks like a high-value prospect, personalize more,”
- “this company seems enterprise, choose a more aggressive research path,”
- “insufficient results, go explore adjacent sources and infer.”

That second category is where you’ve started embedding judgment.

**Priya Raman:** Packaging matters here. Pure managed execution is priced like infrastructure: usage, markup, maybe seats. Single capability delivery can justify a premium because it reduces integration cost and code maintenance. Composed outcomes can justify much higher pricing **if** the value is obvious. But be careful: revenue and margin are not the same.

Every composed capability also creates:
- support cost,
- observability cost,
- QA cost,
- doc cost,
- dispute cost,
- product management cost.

The gross margin can look amazing on a spreadsheet while the net contribution is terrible.

**Samir Haddad:** Exactly. Founders overestimate willingness to pay for magical endpoints and underestimate the support tail. The best composed capability businesses are not “do anything” products. They are narrow, frequent, repeatable jobs where the platform’s hidden work is mostly deterministic and the output is easy to validate.

Examples that tend to work:
- enrich a lead,
- validate and route a form submission,
- monitor a page for change,
- extract structured data from a document type,
- normalize contact/company identities.

Examples that look sexy but kill margin:
- “research this market,”
- “find the best prospects,”
- “run outbound for me,”
- “handle my support escalation.”

Those are consulting businesses wearing API clothes.

**Moderator:** Where is the right boundary between the platform and the agent?

**Maya Srinivasan:** The platform should own the **how of execution**, not the **why of business intent**.

**Natalie Romero:** Another test: if a human product manager would need to define success case-by-case, do not hide it in the platform.

**Jonas Meyer:** And if the agent developer can’t reproduce the same behavior using a visible DAG and explicit policy settings, you’re probably over-abstracting.

**Benji Park:** My harsh phrasing: the moment Resolve starts acting like “the agent behind the agent,” it is in the danger zone.

---

### Panel 1 Key Debates

#### Debate 1: Is composed capability delivery the real value layer or a support nightmare?

**Pro-composition (Romero, Xu, Haddad):** Deterministic compositions solve real pain because agents should not reimplement boring glue logic every time. Repetitive multi-step execution is exactly where a platform should create leverage.

**Skeptical (Meyer, Park, Foster):** Only up to a point. The moment the platform starts owning ambiguous business intent, support and blame explode. The agent can no longer tell what failed or why.

**Assessment:** Composition creates real value only when the job is common, bounded, and objectively testable.

#### Debate 2: What is the stable product layer?

**Stable middle layer camp (Srinivasan, Foster, Patel):** Single capability delivery is the durable layer. It is high enough to matter, low enough to remain neutral and debuggable.

**Outcome wedge camp (Romero, Haddad):** Some customers will pay most for outcomes, not capabilities. But those outcomes must be tightly productized, not open-ended.

**Assessment:** The stable default product is single capability delivery; outcome delivery should be a carefully limited expansion, not the default surface.

#### Debate 3: Should Resolve hide the composition entirely?

**No-hiding camp (nearly unanimous):** Hidden orchestration becomes anti-trustworthy fast. Trace, provenance, and provider disclosure should be core product features.

**Minor nuance (Cole):** Some low-risk internal routing can remain implicit — e.g. retry, region choice, rate-limit failover — as long as it does not change the semantic contract.

**Assessment:** Hidden policy routing is acceptable in small doses. Hidden multi-step semantic orchestration is not.

---

## Panel 2: Agent UX / Systems / Strategy Thinkers

### Panelists

1. **Dr. Leah Gold** — agent interaction researcher, studies tool-use abstraction in LLM systems  
2. **Nikhil Bansal** — protocol designer for agent-native execution interfaces  
3. **Avery Stone** — developer tools PM focused on AI agent UX  
4. **Prof. Milan Kovac** — systems thinker studying abstraction stability and semantic drift  
5. **Daria Elson** — API product strategist, ex-Plaid / ex-Twilio  
6. **Omar Khouri** — marketplace economist for AI tooling ecosystems  
7. **Tessa Liang** — agent reliability researcher, specialized in planning vs tool execution boundaries  
8. **Reid Calder** — infra founder, now advisor to multiple agent-platform startups  
9. **Sofia Mercer** — product lead in human-in-the-loop agent systems  
10. **Dr. Imani Brooks** — researcher in interface legibility, explanation, and trust in autonomous systems

---

### Session Transcript: What do agents actually want to ask for?

**Moderator:** The hypothesis is that agents don’t want to ask for providers. They want to ask for capabilities or outcomes. True?

**Dr. Leah Gold:** Partly true, dangerously incomplete. Agents do not want to think in provider names **by default**. That does not mean they never want provider-level control. Agents want the abstraction that best matches the current uncertainty of the task.

When uncertainty is low, high-level capability is great. When uncertainty is high, they need more control.

So the right question is not “provider or outcome?” It is: **at what level can the task be specified without losing recoverability?**

**Nikhil Bansal:** Exactly. In protocol design, a good abstraction is one that hides incidental complexity but preserves the control points needed for correction. The problem with many “outcome” APIs is not that they are high-level. It’s that they hide the wrong things.

A stable agent interface should expose:
- intent,
- constraints,
- policy knobs,
- trace,
- override points.

Without those, you don’t have abstraction. You have wishful delegation.

**Avery Stone:** From an agent UX perspective, the winning pattern is usually **progressive disclosure**:
- default to capability,
- allow provider pinning,
- allow policy preferences,
- surface execution trace and artifacts,
- let the agent drop down a layer when needed.

That’s how you avoid making agents choose between convenience and control.

**Prof. Milan Kovac:** The most stable abstraction is often not the most human-sounding one. “Send an email” is fairly stable. “Research this company” is not. “Find a prospect and enrich it” is partially stable but only if you define what counts as success and what the output contract is.

This is the core mistake many AI platforms make: they use natural language labels for products whose semantics are still unstable.

**Moderator:** So where is the stable abstraction?

**Daria Elson:** The stable middle is the normalized capability with typed constraints. Think:
- `email.send(message, recipient, channel_policy, approval_mode)`
- `person.enrich(identifier, desired_fields, freshness_requirement)`
- `document.parse(file, schema, extraction_strategy)`

These are understandable, high-value, and still contractable. Once you move to “get me a great prospect” or “do the research,” the output quality depends heavily on context and judgment.

**Omar Khouri:** But don’t underrate demand for outcomes. Buyers don’t naturally think in primitives. They think in jobs. The reason outcome delivery keeps returning as a thesis is because it is often where budget lives. Nobody says, “I have budget for provider normalization.” They say, “I need leads,” “I need monitoring,” “I need support resolution,” “I need briefs.”

So the market pull is real. The mistake is assuming demand proves abstraction stability.

**Tessa Liang:** In agent systems, there is also a loop-shape issue. If the agent can cheaply call tools multiple times, it may prefer primitives because it can adapt. If the agent is ephemeral, cost-sensitive, or context-limited, it may prefer higher-level capabilities to avoid planning overhead.

This means the answer is segmentation-dependent:
- sophisticated persistent agents often want primitives plus a few shortcuts,
- ephemeral agents want more packaged capabilities,
- enterprise agents want strong auditability regardless.

**Reid Calder:** I want to sharpen the minority view because it’s important: **agents want primitives, not hidden workflows.** That view is stronger than people think.

The reason is not ideological. It’s operational. Primitives make failures local. Hidden workflows make failures global and ambiguous. If I call `search.query` and get bad results, I know what to adjust. If I call `company.research_brief` and it’s weak, was it the search, extraction, summarization, ranking, or prompt template? If the answer is “trust us,” serious agent developers will churn.

**Sofia Mercer:** I’d soften that slightly. Agents don’t want *only* primitives. They want **primitives where correctness is fragile** and **higher-order packaged capability where the platform has earned trust**.

Think about GPS. Humans want “navigate me there,” not raw map tiles. But only after the system proves it can explain the route, reroute predictably, and let you override. The analogy for Resolve is not “never compose.” It’s “don’t claim navigation quality until you have roads, traffic, and rerouting under control.”

**Dr. Imani Brooks:** Legibility is the key. Users tolerate invisible complexity when the system remains legible under failure. That means:
- visible step list,
- visible providers used,
- visible artifacts,
- confidence and uncertainty,
- visible fallback choice,
- visible approval boundaries.

If an agent developer can inspect and reason about the path after the fact, they are much more willing to use higher abstraction.

**Moderator:** What about the argument that outcome delivery is the real wedge?

**Omar Khouri:** It can be the wedge in go-to-market terms. Higher-level outcomes map better to budgets and business buyers. But it is rarely the first stable platform layer.

The sequence I usually see work is:
1. build trust on primitives or normalized capabilities,
2. learn the task distribution,
3. identify repeated multi-step patterns,
4. productize only those patterns.

Going straight to outcomes often means you skip the data needed to know where the abstraction is safe.

**Leah Gold:** Another reason the “outcome wedge” is risky: agents are not just buyers, they are also orchestrators. If Resolve goes too high-level too early, it competes with the agent’s own planning layer. Then the agent developer has two planners to coordinate: their own agent and Resolve’s implicit internal planner. That’s a recipe for conflict and redundant complexity.

**Nikhil Bansal:** Which leads to a strong design principle: **one planner of business intent, many execution helpers.**

If the top-level business planning is already in the agent, Resolve should not secretly become a second planner. It should be an execution substrate with optional compiled workflows.

**Avery Stone:** “Compiled workflows” is the right phrase. The best composed capabilities are basically pre-compiled, observable, parameterized subroutines for common tasks. They are not mini-agents improvising under the hood.

**Prof. Milan Kovac:** I’d go further: the abstraction becomes stable only when the possible internal variation is narrower than the user’s tolerance for surprise. That sounds abstract, but it has practical consequences.

Good candidate:
- page monitoring: users tolerate many implementation details as long as the diff is right and notifications are timely.

Bad candidate:
- prospecting: users care deeply about source quality, selection criteria, ranking rationale, and confidence. Surprise is expensive.

**Moderator:** Final question: if Resolve offered all three layers, what should be the default surface?

**Daria Elson:** Single capability delivery.

**Sofia Mercer:** Single capability with trace.

**Reid Calder:** Raw access and capability side by side. Never force abstraction.

**Omar Khouri:** Commercially, lead with capability and selected composed outcomes by vertical use case.

**Leah Gold:** Architecturally: capability-first, composition-second, raw access always available.

---

### Panel 2 Key Debates

#### Debate 1: Do agents want primitives or outcomes?

**Primitives-first minority (Calder, Kovac):** Serious agent builders want low-level control because hidden workflows destroy debuggability and create stacked planning problems.

**Outcome-demand camp (Khouri, Mercer):** Buyers and many lightweight agents do want outcomes, especially where the task maps to a clear business job.

**Synthesis:** Agents want both, but at different moments. The product should not force a single abstraction level.

#### Debate 2: Where is the stable abstraction?

**Strong consensus:** The most stable broad layer is **single capability delivery**. It hides vendor mess while preserving a contract.

**Qualified extension:** Some deterministic higher-order capabilities can also become stable, but only category by category after real usage data and explicit contracts.

#### Debate 3: Should Resolve own planning?

**No-planner camp (Bansal, Gold, Calder):** Resolve should not be the hidden business planner. That conflicts with the agent’s role.

**Compiled-subroutine camp (Stone, Mercer):** Resolve can own pre-compiled, bounded, parameterized workflows that act like tool macros, not independent planners.

**Assessment:** Resolve should own execution intelligence, not open-ended business planning.

---

## Panel 3: Adversarial / Red Team / Reliability / Neutrality

### Panelists

1. **Rachel Stein** — trust and safety lead for a high-volume API platform  
2. **Marcus Iqbal** — legal and platform-risk advisor, specialized in AI agent liability  
3. **Yvonne Delgado** — reliability engineer for automation systems in regulated industries  
4. **Simon Beck** — marketplace neutrality analyst, studied ranking and routing conflicts  
5. **Asha Nwosu** — security engineer focused on prompt injection and tool-chain compromise  
6. **Daniel Kruger** — provider partnerships executive, ex-platform BD lead  
7. **Priyanka Sen** — abuse prevention architect for multi-tenant execution systems  
8. **Gareth Liu** — red team operator for autonomous workflows  
9. **Monica Fraley** — enterprise procurement and vendor-risk consultant  
10. **Ilan Romero** — incident commander for distributed orchestration systems

---

### Session Transcript: Does multi-step composition make Resolve more valuable or just more dangerous?

**Moderator:** Assume Resolve starts offering composed capabilities like `research.company`, `prospect.find_and_enrich`, or `page.monitor_and_notify`. What new danger enters the system?

**Rachel Stein:** The first danger is **responsibility laundering**. When a platform hides multiple steps behind one high-level action, users stop knowing where responsibility lies. Then when something goes wrong, the platform becomes the universal blamed party even if one upstream provider or the agent’s own prompt caused the problem.

That is manageable only when the platform gives users a receipt of what actually happened.

**Marcus Iqbal:** Legally and contractually, composition changes what you are promising. If you offer `email.send`, you are clearly an execution intermediary. If you offer `prospect.find_and_enrich`, you are closer to representing that the selected prospect and enrichment are fit for use. If you offer `research.company`, you are creeping toward information-quality claims.

Law is not just triggered by your intent. It is triggered by how a reasonable customer interprets your product promise.

**Yvonne Delgado:** Reliability risk changes shape under composition. There are classic infrastructure failures — timeouts, retries, 5xx, bad auth. Then there are composition-specific failures:
- stale intermediate state,
- duplicated side effects,
- step-order bugs,
- mismatched schemas between steps,
- one step succeeding while the next silently degrades quality,
- hidden fallback changing output semantics,
- retry causing a second irreversible action.

These are harder because the system often returns *something*. It just isn’t trustworthy.

**Simon Beck:** Neutrality is the big strategic issue. Rhumb’s moat is trust. Hidden composition is where neutrality goes to die if you’re careless.

If Rhumb both:
- scores providers publicly, and
- routes composed outcomes internally,

then every provider and customer will ask whether routing is truly neutral or financially influenced. If Rhumb says “we’re neutral” but silently prefers partners, margin-rich vendors, or vendors with better kickbacks, it corrupts the brand.

Worse, even if Rhumb is behaving honestly, opaque routing will make it impossible to prove.

**Asha Nwosu:** Security gets worse in two ways. First, the more steps you compose, the larger the attack surface. Second, higher-level capabilities often require carrying data across systems that weren’t previously linked.

Example:
- web content from a crawl step flows into extraction,
- extraction flows into summarization,
- summary flows into email drafting,
- email draft flows into send.

Now a prompt injection or malicious artifact in the crawl can poison later steps. If the user only asked for “research and notify,” they may not realize how much untrusted data got transitively trusted.

**Daniel Kruger:** Provider relationships also get more delicate. Providers tolerate being one ingredient in a stack as long as attribution, usage boundaries, and customer expectations are fair. But if Resolve hides them completely and presents the whole outcome as “Rhumb magic,” providers will worry they are commoditized into replaceable cogs.

Some providers won’t care. Some will. The more strategic the category, the more they’ll care.

**Priyanka Sen:** Abuse patterns get nastier too. A raw provider endpoint is usually easy to meter and bound. A composed capability can become a cost amplifier. One innocent-looking request may fan out to five vendors, scrape multiple pages, run extraction, then send notifications. Bad actors love hidden fan-out because it obscures cost and policy violations.

You need per-step policy budgets, not just per-request budgets.

**Gareth Liu:** Red team perspective: the worst pattern is hidden irreversible side effects after hidden open-ended exploration. Example:
- agent asks `find_best_prospect_and_email`
- system researches widely, picks a person, drafts message, sends it
- user later says “why did you contact my competitor’s former employee with false assumptions?”

That is not an infrastructure failure. That is a trust collapse.

The product should treat **irreversible external action** as a hard boundary requiring explicit review or at least a separately visible stage.

**Monica Fraley:** Enterprise buyers care less about whether composition is clever and more about whether it is governable. They ask:
- Can I inspect the path?
- Can I pin providers?
- Can I disable certain steps?
- Can I force approval before external actions?
- Can I export logs for audit?
- Can I know where data went?

If the answer is no, many enterprises will reject high-level composition outright.

**Ilan Romero:** Incident response becomes significantly harder under composition because you need cross-step observability. You don’t just need request logs. You need:
- plan version,
- policy version,
- provider sequence,
- intermediate artifacts,
- retry history,
- compensation actions taken,
- human approvals encountered.

Without that, you cannot explain incidents. And if you cannot explain incidents, you cannot be trusted with important workflows.

**Moderator:** Is multi-step composition worth it anyway?

**Rachel Stein:** Yes, but not by default. The right model is **declared composition**. The agent should know when it is invoking a composite capability, what class of steps may happen, and what side-effect boundaries exist.

**Marcus Iqbal:** I would draw a legal/product line between three things:

1. **Routing abstraction** — low added legal risk.  
2. **Deterministic composition with read-heavy or reversible behavior** — manageable risk.  
3. **Open-ended agentic workflow with judgment and irreversible actions** — dramatically higher risk.

That third category is where customer expectation, negligence arguments, and contract language get hairy fast.

**Simon Beck:** From a neutrality standpoint, Rhumb must never mix “trusted neutral layer” branding with undisclosed routing economics. If there is revenue share, preferred partner treatment, or package-based vendor preference, that needs explicit policy and disclosure.

**Priyanka Sen:** Also, composition creates new fraud vectors. Attackers can use high-level endpoints to trigger more provider spend than is obvious. Or they can craft inputs that maximize fan-out. Or they can exploit retries to duplicate costly substeps. Cost ceilings and step-level quotas are mandatory.

**Asha Nwosu:** And provenance must be security provenance too. Not just “which provider was used,” but “which data artifact entered where.” That matters for prompt injection, data exfiltration, and cross-tool contamination.

**Moderator:** What is the anti-trustworthy line? The point beyond which hidden orchestration becomes dangerous?

**Gareth Liu:** My rule: once the hidden internal workflow materially changes the meaning of the user’s request, it’s too hidden.

If `search.query` silently chooses a different search provider, fine. If `email.send` silently decides to enrich the person, infer intent, personalize the message, and change send timing, not fine.

**Monica Fraley:** Another rule: if the workflow involves multiple data processors or outbound action to a third party, disclose it. Procurement teams will insist on it anyway.

**Ilan Romero:** And operationally: if a human responder would need the internal trace to debug it, the user needs access to that trace too.

---

### Panel 3 Key Debates

#### Debate 1: Is composition mostly a trust risk?

**Risk-heavy camp (Stein, Beck, Nwosu, Liu):** Composition is dangerous by default because it expands hidden behavior, attack surface, and ambiguity.

**Qualified yes camp (Delgado, Fraley, Romero):** It is acceptable when declared, observable, reversible where possible, and constrained away from ambiguous or irreversible actions.

**Assessment:** Composition is not inherently untrustworthy. Hidden, unbounded composition is.

#### Debate 2: Can Resolve remain neutral while composing?

**Skeptical camp (Beck, Kruger):** Only with strong disclosure, route explainability, provider pinning, and policy separation between scoring and routing.

**Pragmatic camp (Fraley, Iqbal):** Enterprises will tolerate composition if governance is strong and routing policies are controllable.

**Assessment:** Neutrality is preserved only if routing logic is inspectable and commercial incentives are disclosed or structurally separated.

#### Debate 3: Should Resolve ever own irreversible outcome execution?

**Hard caution (Liu, Nwosu, Iqbal):** Not without explicit approval boundaries and a visible staged plan.

**Limited allowance (Stein, Delgado):** Yes for narrow, well-understood operations with strong guardrails, such as sending a notification to a user-defined destination.

**Assessment:** Resolve should avoid hidden irreversible external actions inside composed capabilities unless the step is explicit and policy-governed.

---

## Synthesis: Direct Answers

### 1. Do agents actually want this?

**Direct answer:** **Agents want some of this, not all of this.**

More precisely:

#### What agents clearly want

**A. They want to stop thinking about vendors when vendor choice is incidental.**  
Most agents do not want to carry around provider-specific schemas, auth peculiarities, and rate-limit logic when the task is simply “search the web,” “send a message,” or “parse a document.” This is the strongest and most consistent demand signal.

**B. They want shortcuts for repetitive multi-step chores.**  
If a task is a routine braid of multiple boring steps, agents do not want to re-orchestrate it every time. They want precompiled helpers.

**C. They want fallback and routing intelligence.**  
Agents like asking for `search.query` and getting the platform’s help with provider selection, retries, or budget policy.

**D. They want auditability and the ability to override.**  
Even agents that love abstraction want the ability to inspect the trace, pin a provider, or re-run lower in the stack when something smells wrong.

#### What agents do **not** broadly want

**A. They do not want hidden open-ended workflows pretending to be simple tools.**  
If the platform silently becomes another planner, the agent developer loses predictability.

**B. They do not want abstraction that removes debuggability.**  
If the agent cannot tell why output quality was bad, trust erodes quickly.

**C. They do not want irreversible actions hidden inside high-level “outcome” verbs.**  
Especially for email, CRM mutation, money movement, security changes, or public posting.

#### Segmentation matters

Different agents want different layers:

- **Sophisticated vertical agents:** want raw + capability + selected compositions.
- **Ephemeral lightweight agents:** want more capability-level packaging, fewer primitives.
- **Enterprise agents:** want capability-level defaults with visible governance controls.
- **Experimental consumer-style agents:** may love outcomes in demos, but are unreliable reference customers for product architecture.

#### The precise answer Rhumb should use internally

**Agents do not want “outcomes” as a blanket abstraction. They want the highest stable abstraction that still preserves control, traceability, and correction.**

That is usually:
- raw access for specialist work,
- single capability for default work,
- explicit deterministic composition for a narrow subset of repetitive jobs.

### 2. Is this a better business than pure managed execution?

**Direct answer:** **Yes, but only if Rhumb stays in the narrow band where composition is repeatable and trustworthy. Otherwise no.**

#### Why pure managed execution is attractive

- operationally cleaner,
- easier to explain,
- easier to price,
- more neutral,
- lower legal risk,
- better provider relationships,
- clearer success metric: request executed correctly.

#### Why pure managed execution is limited

- thinner margins,
- weaker wedge against commoditization,
- lower willingness to pay,
- easier for large providers to bypass,
- less sticky because the agent still owns most application logic.

#### Why single capability delivery is the best business layer

- it captures real product value,
- it reduces agent developer work materially,
- it remains contractable and debuggable,
- it creates stickiness without overpromising,
- it allows packaging and margin expansion.

#### Why composed capability delivery is only conditionally better

It becomes a better business only when:
- the task frequency is high,
- the workflow is stable,
- output can be judged objectively,
- support burden stays bounded,
- liability is manageable,
- customers trust the trace,
- provider relations are preserved.

It becomes a worse business when:
- the task is ambiguous,
- success is subjective,
- context is business-specific,
- errors are expensive or embarrassing,
- hidden orchestration makes debugging impossible,
- you are competing with the agent’s planning layer.

#### Therefore

**The better business is not “be an outcome platform.” The better business is “own execution and capability normalization, then selectively capture margin on deterministic compositions where Rhumb can be measurably better than every customer rebuilding the same workflow badly.”**

---

## Framework: Raw Access vs Single Capability vs Composed Capability

### Layer comparison matrix

| Dimension | Raw provider/tool access | Single capability delivery | Composed / multi-step capability delivery |
|---|---|---|---|
| User request | “Use provider X” | “Do capability Y” | “Achieve outcome Z” |
| Promise | Vendor control | Stable job category | Higher-order result |
| Typical hidden logic | Minimal | routing, retries, normalization | multiple steps, multiple providers, policy flow |
| Debuggability | Highest | High if trace exists | Low to medium unless trace is excellent |
| Neutrality risk | Low | Medium | High |
| Provider relationship risk | Low | Medium | High |
| Support burden | Low | Medium | High |
| Margin potential | Low to medium | Medium to high | High gross, uncertain net |
| SLA clarity | Clear | Mostly clear | Often murky |
| Best for | experts, power use | default product surface | selected repeated workflows |
| Bad for | non-experts who hate vendor sprawl | highly ambiguous tasks | open-ended judgment-heavy work |

### The key insight about these three layers

They are **not substitutes**. They are a stack.

- Raw access is the escape hatch and trust anchor.
- Single capability is the default product surface.
- Composed capability is the optional premium layer.

If Rhumb removes raw access, it loses power users and debuggability.  
If Rhumb skips capability and jumps to outcomes, it overreaches.  
If Rhumb never adds composition, it may leave margin and stickiness on the table.

### What each layer should optimize for

#### Raw provider/tool access should optimize for:
- fidelity,
- transparency,
- low surprise,
- provider pinning,
- near-provider docs and semantics.

#### Single capability delivery should optimize for:
- stable schemas,
- stable error envelopes,
- policy knobs,
- routing trace,
- sensible fallbacks,
- consistent billing.

#### Composed capability delivery should optimize for:
- declared workflow class,
- deterministic step graph,
- strong artifacts and provenance,
- step-level budgets,
- clear partial-failure states,
- user-visible approval and side-effect boundaries.

### The hidden mistake to avoid

The biggest category error would be to use the same API design and trust model for all three layers. They need different product semantics.

For example:
- `search.query` can safely allow silent provider fallback in many cases.
- `prospect.find_and_enrich` cannot safely hide source selection, confidence ranking, or verification path.
- `send_email` should almost never hide enrichment + personalization + send timing decisions unless the user explicitly invoked that composite mode.

---

## Which Categories Are Good Candidates for Composition vs Bad Candidates

The panel pushed hard for categorization by **stability**, **reversibility**, **subjectivity**, and **blast radius**.

### Best candidates for composition

These categories scored well because the value of hiding boring plumbing is high and the trust risk is manageable.

#### 1. Monitoring and notification
Examples:
- `page.monitor_and_notify`
- `api.monitor_and_alert`
- `job.monitor_and_report`

Why good:
- mostly read-heavy until notification,
- objective success criteria,
- clear artifacts (before/after snapshots, diffs),
- deterministic scheduling and threshold logic.

Guardrails:
- visible diff criteria,
- explicit notification destinations,
- no silent expansion in scope.

#### 2. Document intake and extraction
Examples:
- `document.ingest_and_extract`
- `invoice.parse_and_validate`
- `resume.extract_to_schema`

Why good:
- bounded input types,
- output schema can be specified,
- validation is possible,
- multi-step internals are mostly mechanical.

Guardrails:
- schema contract,
- confidence per field,
- artifact retention,
- human review option for low confidence.

#### 3. Lead / contact enrichment pipelines
Examples:
- `person.find_and_enrich`
- `company.resolve_and_enrich`

Why conditionally good:
- recurring problem,
- deterministic joins and fallbacks exist,
- users hate rebuilding it.

Why still tricky:
- source quality matters,
- confidence matters,
- false positives are expensive.

Required guardrails:
- ranked candidates,
- confidence scores,
- source provenance,
- ability to disable aggressive guessing.

#### 4. Form intake → validation → routing
Examples:
- `lead.capture_score_route`
- `submission.validate_and_dispatch`

Why good:
- highly repetitive,
- mostly rules-based,
- strong economic value,
- measurable success.

Guardrails:
- explicit scoring logic,
- deterministic routing policy,
- audit logs.

#### 5. Web snapshot → extract → summarize for a narrow template
Examples:
- `company.brief_from_homepage`
- `pricing.page_extract`

Why conditionally good:
- useful shortcut,
- repeated shape,
- output can be provenance-backed.

Guardrails:
- constrain source scope,
- expose citations,
- avoid implying comprehensive research.

### Medium candidates: compose carefully

#### 6. Research briefs
Examples:
- `company.research_brief`
- `competitor.summary`

Why medium:
- very attractive from a product perspective,
- buyers love it,
- but semantic drift is high.

The platform can do this only if it is explicit that the output is a **sourced brief**, not “truth.” The more the platform implies judgment, the more dangerous it gets.

#### 7. Prospecting workflows
Examples:
- `prospect.find_and_enrich`
- `account_list.build`

Why medium:
- high buyer willingness to pay,
- strong wedge potential,
- but correctness is not binary.

The risk is turning a deterministic execution layer into a fuzzy sales-judgment engine.

### Bad candidates for composition

These are the categories the panel viewed as high-risk or strategically wrong for Resolve.

#### 1. Irreversible external communications without review
Examples:
- `find_best_prospect_and_email`
- `support.reply_to_customer`
- `post_and_promote`

Why bad:
- compound failure + reputational harm,
- hidden assumptions,
- subjective quality,
- easy trust collapse.

Recommended stance:
- split drafting from sending,
- make sending an explicit separate action with approval.

#### 2. Money movement or financially consequential actions
Examples:
- `invoice_customer_and_charge`
- `refund_based_on_signal`
- `reconcile_and_pay`

Why bad:
- high liability,
- regulated consequences,
- retry/idempotency and fraud issues,
- little tolerance for ambiguity.

Recommended stance:
- keep money steps explicit and separately approved.

#### 3. Security or infrastructure mutation
Examples:
- `investigate_and_patch`
- `rotate_compromised_credentials_and_notify`

Why bad:
- huge blast radius,
- hidden orchestration dangerous,
- requires operator intent and context.

Recommended stance:
- use Resolve as a tool surface, not as an autonomous incident responder.

#### 4. Legal, HR, or policy judgments
Examples:
- `screen_candidate`
- `moderate_for_policy_violation_and_ban`
- `assess_contract_risk`

Why bad:
- subjective and jurisdiction-sensitive,
- high liability,
- trust and fairness concerns.

#### 5. Open-ended business strategy tasks
Examples:
- `research_this_market`
- `identify_best_customers`
- `run_my_outbound`

Why bad:
- consulting disguised as API,
- impossible to contract cleanly,
- endless support tail.

### Composition suitability rubric

A category is a good composition candidate if most of the following are true:

- high task frequency,
- repeated workflow shape,
- objective output checks,
- mostly read-heavy or reversible,
- low legal sensitivity,
- bounded number of steps,
- stable source set,
- easy provenance display,
- low reputational blast radius,
- clear fallback policy.

It is a bad candidate if most of these are true:

- success is subjective,
- irreversible external action,
- high-context judgment,
- regulated consequences,
- open-ended exploration,
- broad source ambiguity,
- hidden personalization or ranking,
- difficult postmortems.

---

## Where Composition Should Live: Agent, Rhumb, or Hybrid

This was the most important product-boundary discussion in the whole panel.

### Strong recommendation

**Composition should live in three places depending on the kind of logic involved.**

#### 1. Composition that should live in Rhumb

This is infrastructure or compiled-execution logic that many agents would otherwise duplicate poorly.

Examples:
- provider routing,
- retries and fallback,
- budget-aware provider selection,
- schema normalization,
- deterministic validation chains,
- known read-heavy workflow recipes,
- artifact capture and provenance.

Why Rhumb should own it:
- economies of scale,
- consistency,
- shared learning across customers,
- better operational tuning,
- better cost control.

#### 2. Composition that should live in the agent

This is business-contextual logic requiring judgment, prioritization, or bespoke strategy.

Examples:
- deciding whether to contact a lead,
- determining what “good enough research” means,
- choosing tradeoffs between speed and thoroughness based on account value,
- adapting workflow based on company-specific or user-specific context,
- interpreting ambiguous results.

Why the agent should own it:
- it has the task context,
- it owns the business goal,
- it can decide when to branch, stop, escalate, or ask for review.

#### 3. Composition that should be hybrid

This is the sweet spot.

Pattern:
- the agent decides **what outcome class it wants**,
- Rhumb executes a declared deterministic recipe,
- the agent can inspect artifacts, adjust knobs, or drop down to lower levels.

Examples:
- `prospect.find_and_enrich` with configurable search scope, confidence threshold, and verification mode,
- `page.monitor_and_notify` with explicit selectors, frequency, and channels,
- `document.ingest_and_extract` with schema + validation policy.

Why hybrid wins:
- Rhumb captures the boring plumbing,
- the agent keeps intent and judgment,
- debuggability is preserved.

### Product boundary table

| Logic type | Best owner |
|---|---|
| Auth, credentials, billing | Rhumb |
| Provider routing / fallback | Rhumb |
| Normalized capability schemas | Rhumb |
| Deterministic recipe execution | Rhumb or hybrid |
| Business prioritization | Agent |
| Ambiguous task interpretation | Agent |
| Final approval on irreversible actions | Agent / human policy layer |
| Cross-task memory and strategic planning | Agent |
| Compliance policy specific to org | Shared, but agent/org policy leads |

### The sharpest rule from the panel

**Rhumb should compile workflows, not improvise business intent.**

That single sentence is probably the cleanest architecture rule for Resolve.

---

## Neutrality, Trust, and Provider Relationships

Resolve’s strategic advantage is not merely convenience. It is **trusted neutrality** around tool access, discovery, and execution. Composition can strengthen that moat — or quietly poison it.

### How composition threatens neutrality

#### 1. Hidden provider preference
If Rhumb routes high-level outcomes toward providers with better margins, rebates, partnerships, or simpler integration while claiming neutrality, the trust surface is corrupted.

#### 2. Invisible commoditization of providers
Providers will tolerate being abstracted if customers still understand where value came from. They become hostile when they feel stripped of attribution and turned into invisible replaceable cogs.

#### 3. Scoring vs routing conflict
If Rhumb publicly scores providers with AN Score but internally routes differently for economic reasons, customers and providers will assume the score is marketing, not truth.

#### 4. Hidden semantics changes
If composition silently changes what a request means, users will feel manipulated even when the result is nominally useful.

### How composition can preserve trust instead

#### A. Separate scoring from routing policy
AN Score and public trust evidence should remain independent from commercial routing policy. If a route differs from the highest-scoring provider, the system should be able to explain why:
- user-pinned provider,
- lower cost cap,
- region or data residency,
- outage / quota / latency constraint,
- required feature not available elsewhere.

#### B. Show execution receipts
Every capability invocation above raw provider level should have a receipt:
- capability requested,
- plan or recipe version,
- providers used,
- intermediate steps,
- cost and time,
- fallback or retries,
- artifacts,
- confidence / warnings.

#### C. Allow provider pinning and policy control
Users should be able to say:
- “use only provider X,”
- “prefer providers with AN Score above threshold,”
- “do not use provider Y,”
- “no data leaves region Z,”
- “never send without approval.”

#### D. Declare composition classes
If something is composite, call it composite. Don’t smuggle it inside a deceptively simple primitive.

### Provider relationship implications

Providers will react differently by category:

#### Providers likely to be comfortable
- long-tail tools that benefit from aggregated demand,
- providers with weak developer distribution,
- tools happy to be normalized into a broader capability market.

#### Providers likely to become sensitive
- strategic categories like model providers, search, messaging, payments,
- vendors building their own agent surfaces,
- providers with strong brand and enterprise ambitions.

### The practical rule Rhumb should adopt

**Resolve can abstract providers, but it cannot erase them.**

That means:
- execution receipts should preserve attribution,
- docs should acknowledge provider options,
- routing policy should be explainable,
- commercial incentives should not be hidden inside trust claims.

---

## Economics and Margin Potential

This section was where the panel got most specific.

### The economic ladder

#### 1. Raw managed execution
Revenue model:
- usage markup,
- subscription for access / trust / billing consolidation,
- maybe seats or enterprise support.

Strengths:
- simplest to price,
- clearest cost basis,
- easier gross margin modeling.

Weaknesses:
- low differentiation over time,
- easier to compress on price,
- vulnerable if providers improve direct agent access.

#### 2. Single capability delivery
Revenue model:
- usage + higher take rate,
- premium for normalization and reliability,
- tiered packaging by SLA / routing / trace / governance.

Strengths:
- higher willingness to pay than raw routing,
- real switching cost because the contract is stable,
- less code for customers,
- still operationally sane.

Weaknesses:
- requires strong schema design and testing,
- some categories are hard to normalize well.

#### 3. Deterministic composed capability delivery
Revenue model:
- per successful task,
- premium usage,
- workflow subscriptions,
- outcome-based pricing in select categories.

Strengths:
- highest perceived value,
- strongest wedge into budgets,
- higher ARPU per active agent.

Weaknesses:
- hidden internal cost fan-out,
- greater support and QA costs,
- dispute burden,
- potentially much lower net margin than gross margin appears.

### Margin realities by layer

The panel converged on a rough shape, not exact percentages:

#### Raw managed execution
- likely lower gross margin,
- more volume-driven,
- more exposed to provider pricing and competition.

#### Single capability delivery
- best balance of margin and operational control,
- enough value add to justify premium,
- lowest risk of margin erosion from support.

#### Composed deterministic delivery
- potentially the highest contribution margin **if** the workflow is tight,
- potentially the worst business **if** every task becomes a custom support case.

### Why composition can increase margins

Composition adds economic value when it lets Rhumb capture:
- orchestration know-how,
- shared workflow intelligence,
- reduced customer engineering effort,
- lower internal execution cost through optimized routing,
- packaging against business jobs instead of raw API calls.

### Why composition can destroy margins

It destroys margins when:
- one request fans out to many provider calls unpredictably,
- retries or fallbacks multiply cost silently,
- users dispute result quality,
- human review becomes necessary,
- docs and product work become bespoke per category,
- support team becomes workflow consultants.

### The best economic model for Resolve

The most credible structure from the panel was:

#### Base layer: managed execution / control plane
- thin usage economics,
- trust, auth, credentials, billing, routing.

#### Product layer: single capability delivery
- main revenue and packaging surface,
- stable contracts,
- premium for normalized capability + policy + observability.

#### Select premium layer: deterministic compositions
- a small catalog of high-frequency recipes,
- priced by successful outcome or bundled in premium plans,
- only where cost envelopes are predictable.

### The anti-pattern to avoid economically

**Do not build a broad “just ask for any outcome” layer and assume margin follows automatically.**

That is how you end up with:
- demo excitement,
- unclear cost basis,
- rapidly growing support load,
- customers angry about variance,
- providers unhappy about opaque routing,
- internal team buried in exceptions.

### Business conclusion

**Single capability delivery is likely the highest-quality business for Resolve in the next phase. Composed capability delivery is an expansion layer, not the core business model.**

---

## What Resolve Should Be NOW vs LATER vs NEVER

### NOW

#### 1. Keep raw provider/tool access as a first-class surface
This is essential for:
- trust,
- debugging,
- power users,
- provider pinning,
- proving that Resolve is not locking users into black-box behavior.

#### 2. Make single capability delivery the primary product surface
Resolve should aggressively productize normalized capabilities such as:
- `search.query`
- `person.enrich`
- `company.enrich`
- `document.parse`
- `page.capture`
- `monitor.check`
- `email.send`

But with visible constraints, knobs, and trace.

#### 3. Add only 2-5 deterministic composed capabilities now
Pick narrow, repetitive, tractable workflows. Likely candidates:
- `page.monitor_and_notify`
- `document.ingest_and_extract`
- `company.resolve_and_enrich`
- `submission.validate_and_route`

These should be explicit composite products, not hidden behind unrelated primitives.

#### 4. Build the trust surface before expanding the composition surface
Before adding many composed capabilities, ship:
- execution receipts,
- provider disclosure,
- route explanations,
- policy knobs,
- partial-failure states,
- cost visibility,
- approval boundaries.

#### 5. Separate “compile-time recipes” from “agent runtime planning”
This should appear in docs and product language. Resolve recipes are bounded and deterministic. Resolve is not secretly planning open-ended business tasks.

### LATER

#### 1. Expand the composed capability catalog selectively
Only after observing real repeated usage patterns and support tickets.

#### 2. Introduce recipe versioning and governance
Each composed capability should have:
- versioned plan definitions,
- policy presets,
- changelogs,
- replay tools,
- org-level guardrails.

#### 3. Offer configurable routing and quality/cost policy packs
Examples:
- cheapest,
- best AN Score,
- fastest,
- region-restricted,
- conservative confidence mode.

#### 4. Build vertical packs only after base abstractions are stable
Example packs:
- GTM / lead ops,
- web monitoring,
- document intake,
- support triage.

But only once the underlying capabilities and traces are reliable.

#### 5. Consider outcome-style packaging only where the workflow truly behaves like a product
Examples:
- website change monitoring,
- form submission routing,
- invoice intake and extraction.

Not generic research or generic outbound.

### NEVER

#### 1. Never make open-ended hidden orchestration the default behavior of ordinary primitives
`email.send` should not secretly become “research, infer, personalize, choose timing, and send.”

#### 2. Never sacrifice provider visibility in the name of abstraction
Rhumb can simplify choice without turning provider usage into an opaque black box.

#### 3. Never let commercial routing quietly contaminate the neutrality story
If there are preferred partners or revenue-share policies, either disclose them or structurally separate them from neutral trust claims.

#### 4. Never promise business outcomes that depend on subjective judgment without making that explicit
“Research this company” and “find the best prospect” cannot be treated like pure infrastructure verbs.

#### 5. Never hide irreversible actions in composed flows without explicit controls
Send, charge, post, delete, mutate, or revoke actions must be separately visible and governable.

---

## Recommended Product Posture in Plain English

If this had to be stated on one internal slide or in one founding memo, it should read like this:

> **Resolve should not try to be the agent.**  
> Resolve should be the trusted execution substrate agents use to access tools at the right level of abstraction.  
> 
> That means three layers:
> - direct provider access when the agent wants control,
> - normalized capability access as the default product,
> - a small set of explicit deterministic multi-step capabilities for repetitive jobs.
> 
> Resolve should add value by compiling boring execution logic, not by hiding open-ended planning.  
> If a workflow materially changes the meaning of the user’s request, uses multiple providers, or performs irreversible actions, the platform must show that openly.  
> Neutrality and traceability are non-negotiable.

That is the posture that preserves Rhumb’s moat while still moving up-stack.

---

## 90-Day Implications if the Thesis Is True

If the thesis is true in its disciplined form — meaning selective deterministic composition is valuable — the roadmap changes immediately.

### 1. Product architecture implication

Resolve needs an explicit separation between:
- provider adapters,
- capability contracts,
- recipe definitions,
- routing policy,
- execution trace / artifacts,
- approval / side-effect boundaries.

This should not stay implicit in code or docs.

### 2. Capability taxonomy implication

Rhumb should define and publish an internal taxonomy like:

#### Layer A: raw providers
- Brave
- Tavily
- Exa
- Apollo
- Firecrawl
- etc.

#### Layer B: normalized capabilities
- `search.query`
- `person.enrich`
- `document.parse`
- `page.capture`
- `notify.send`

#### Layer C: deterministic recipes
- `page.monitor_and_notify`
- `company.resolve_and_enrich`
- `submission.validate_and_route`
- `document.ingest_and_extract`

This forces discipline and prevents accidental semantic creep.

### 3. Execution trace implication

A receipt / trace system becomes urgent, not optional.

For every capability call above raw provider level, record and surface:
- request id,
- capability id,
- recipe version if composite,
- providers used,
- artifacts produced,
- retries / fallbacks,
- cost and latency,
- warnings,
- approval checkpoints,
- final status.

Without this, composition should not expand.

### 4. Policy surface implication

Resolve needs policy knobs, including:
- provider pinning / deny lists,
- cost ceilings,
- confidence thresholds,
- allowed regions,
- approval mode for external actions,
- fallback policy,
- whether hidden provider substitution is allowed.

This is part of the trust product, not just internal control plane plumbing.

### 5. Packaging implication

The likely packaging for the next 90 days should shift to:

#### Default commercial story
“Use Rhumb to call trusted capabilities, not individual vendors.”

#### Trust story
“You can still pin vendors, inspect traces, and see what happened.”

#### Premium story
“For selected repetitive workflows, Rhumb can handle the orchestration for you.”

Not:
- “Tell Resolve anything and it will figure it out.”

### 6. Engineering implication

For the next 90 days, product work should prioritize:

#### Build now
1. **Capability contracts** with stable schemas and error envelopes  
2. **Execution receipts / traces**  
3. **Provider disclosure and route explanation**  
4. **Policy controls**  
5. **Recipe engine for deterministic compositions only**  
6. **Step-level budget / cost accounting**  
7. **Approval boundary framework for irreversible actions**

#### Defer
1. broad natural-language “outcome engine”  
2. open-ended self-planning workflow orchestration  
3. category explosion before trust surface exists

### 7. Go-to-market implication

The messaging should move from:
- “We route API calls for agents”

to:
- “We give agents stable, trusted capabilities with transparent execution.”

That is stronger and more defensible than pure managed execution, while still honest.

### 8. Specific 90-day plan

#### Days 1-15: Architecture and contracts
- freeze the three-layer vocabulary internally,
- define 8-12 priority capability contracts,
- define what counts as raw vs capability vs composite,
- write product rules for when hidden routing is allowed and when disclosure is mandatory.

#### Days 16-30: Trust surface
- ship execution receipt schema,
- ship provider and step trace in API response or follow-up retrieval endpoint,
- add policy controls for provider pinning, cost ceilings, and approval modes.

#### Days 31-45: First deterministic recipe set
Launch only a tiny set, likely:
- `page.monitor_and_notify`
- `document.ingest_and_extract`
- `company.resolve_and_enrich`

Each with:
- explicit recipe version,
- explicit providers used,
- cost envelope,
- artifacts.

#### Days 46-60: Instrumentation and economics
- per-step cost accounting,
- support ticket categorization by layer,
- recipe success vs semantic-success measurement,
- contribution margin by capability and recipe.

#### Days 61-75: Market validation
- test whether customers prefer raw provider, capability, or composite for top workflows,
- collect where they pin providers,
- measure how often traces are opened,
- identify where abstraction breaks trust.

#### Days 76-90: Kill / scale decisions
For each composed capability, decide:
- scale it,
- keep as beta,
- or kill it.

Success criteria should include:
- actual repeat usage,
- low support burden,
- acceptable contribution margin,
- preserved trust / clarity,
- no provider relationship damage.

### 9. The hidden roadmap change

If this thesis is true, Resolve’s roadmap is no longer just “add more providers.” It becomes:
- curate provider layer,
- normalize capability layer,
- selectively compile deterministic recipes.

That is a different product roadmap and a stronger one.

---

## Appendix A: Minority Views That Need to Stay Alive

These arguments should remain active. They are not noise. They are strategic guardrails.

### Minority view 1: “Agents want primitives, not hidden workflows.”

**Best version of the argument:**  
Serious agent builders need local, inspectable failures and exact control. Hidden workflows create stacked planning and destroy debuggability.

**Why it matters:**  
This view prevents Resolve from slipping into abstraction vanity. It is especially important for the most technically sophisticated customers.

**Action implication:**  
Always preserve raw provider access and traceable capability execution.

### Minority view 2: “Composition destroys debuggability.”

**Best version of the argument:**  
Every extra hidden step multiplies the distance between request and diagnosis. If output quality drops, root cause becomes expensive to locate.

**Why it matters:**  
This is often true unless traces, artifacts, and recipe versions are excellent.

**Action implication:**  
No composed capability should ship without first-class observability.

### Minority view 3: “Outcome delivery is the real wedge.”

**Best version of the argument:**  
Budgets and urgency sit at the job-to-be-done level, not the API primitive level. Customers will pay most for “do the thing,” not “route the call.”

**Why it matters:**  
This view is commercially important. It reminds Rhumb not to stop too low in the stack.

**Action implication:**  
Experiment with a small set of high-value deterministic outcome products, but do not generalize too early.

### Minority view 4: “Single capability delivery is the stable middle layer.”

**Best version of the argument:**  
This is the layer where real customer value, stable semantics, and operational tractability overlap.

**Why it matters:**  
This is probably the central truth of the panel.

**Action implication:**  
Capability-first should be the default product strategy.

### Minority view 5: “Resolve should stay a neutral control plane and let agents compose.”

**Best version of the argument:**  
The best long-term moat is neutrality plus trust evidence, not hidden orchestration. Let agents own business logic; let Rhumb own execution and scoring.

**Why it matters:**  
This guards against overreach and keeps the AN Score trust layer intact.

**Action implication:**  
Any move into composition must preserve inspectability, provider visibility, and route neutrality.

---

## Appendix B: Decision Tests for Every Proposed Composed Capability

Before shipping any composed capability, Resolve should force it through these tests.

### Test 1: Is the task shape repetitive?
If every customer wants a materially different version, do not productize it as a composed capability.

### Test 2: Is success objectively testable?
If success is mostly subjective, this belongs in the agent or a human workflow.

### Test 3: Is the workflow mostly deterministic?
If the platform has to improvise or plan broadly, it is too agentic.

### Test 4: Is the blast radius low?
If failure can embarrass a customer, move money, mutate critical systems, or create compliance risk, keep approval boundaries explicit.

### Test 5: Can the full execution trace be shown succinctly?
If not, the abstraction is too opaque.

### Test 6: Is there a stable cost envelope?
If one request can unpredictably fan out into expensive execution, pricing and abuse become ugly.

### Test 7: Can the user pin or constrain providers/policies when needed?
If not, neutrality and governance suffer.

### Test 8: Does the workflow primarily remove boring glue rather than encode business judgment?
If it encodes judgment, the agent should usually own it.

### Test 9: Can the output include provenance and confidence?
If not, trust will be weak.

### Test 10: Would a sophisticated agent developer thank you for this or resent you for hiding it?
This is not a joke. It is a real product smell test.

---

## Appendix C: Risk Registry

| Risk | Probability | Impact | Why it appears under composition | Mitigation | Priority |
|---|---:|---:|---|---|---|
| Hidden workflow destroys trust | High | Critical | user cannot explain output or failure | execution receipts, declared recipes, provider disclosure | P0 |
| Neutrality questioned by providers/customers | High | Critical | routing and scoring appear conflicted | separate scoring from routing, disclose policies, allow pinning | P0 |
| Support burden overwhelms margins | Medium-High | High | semantic disputes replace technical issues | restrict to narrow recipes, measure support by capability | P0 |
| Cost fan-out / abuse amplification | High | High | one request triggers many expensive steps | step budgets, cost ceilings, per-step quotas | P0 |
| Prompt injection across composed steps | Medium | High | untrusted data crosses tool boundaries | provenance tracking, sanitization, step isolation | P1 |
| Provider relationship damage | Medium | High | providers feel hidden / commoditized | attribution, partner policy, route explainability | P1 |
| Duplicate irreversible side effects | Medium | Critical | retries across steps create double-send / double-mutate | idempotency, explicit side-effect stages, approval gates | P0 |
| Product semantics drift | High | Medium | “simple” verbs acquire hidden behavior over time | capability taxonomy, strict versioning, docs discipline | P1 |
| Enterprise governance rejection | Medium | High | no trace / no controls / unknown data flow | policy controls, audit export, approvals | P1 |
| Open-ended scope creep into “agent behind the agent” | High | High | seductive outcome demos expand abstraction beyond safety | product posture guardrails, NEVER list enforcement | P0 |

---

## Final Assessment

### The honest truth

Rhumb is right to challenge the idea that Resolve should be more than a pass-through or reseller. There **is** real value above pure managed execution. But the value does **not** come from becoming a vague black-box outcome engine. It comes from moving up exactly one-and-a-half layers with discipline.

The panel’s honest conclusion is:

1. **Raw provider access must remain available.** It is the trust anchor, debugging layer, and escape hatch.
2. **Single capability delivery should become Resolve’s primary product surface.** This is the stable, monetizable, agent-native middle layer.
3. **Composed capability delivery is worth doing only for a narrow set of deterministic, repetitive, low-liability workflows.**
4. **Open-ended outcome execution should not be Resolve’s product posture.** That path is operationally seductive and strategically dangerous.

### The single most important insight

**The winning abstraction is not “outcomes.” It is “progressive abstraction with receipts.”**

Agents want the highest stable level of abstraction that still lets them understand, constrain, and correct the system.

That means:
- abstraction without opacity,
- orchestration without hidden semantics,
- convenience without surrendering control.

### The one thing to get right

**Do not let Resolve become the hidden planner behind the agent.**

If Rhumb gets that boundary wrong, it will lose debuggability, damage neutrality, strain provider relationships, and turn a promising infrastructure business into a messy pseudo-automation consultancy.

If Rhumb gets it right, Resolve can be meaningfully more valuable than pure managed execution:
- more useful than a proxy,
- more trustworthy than a workflow black box,
- and more defensible than a simple provider marketplace.

That is the narrow but important line to hold.

---

*Panel concluded 2026-03-30. Document version 1.0.*  
*Recommended next review: after first three deterministic recipes are in market or after 90 days, whichever comes first.*
