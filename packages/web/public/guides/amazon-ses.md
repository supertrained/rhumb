# Amazon SES — Agent-Native Service Guide

> **AN Score:** 5.84 · **Tier:** L3 · **Category:** Email Delivery

---

## 1. Synopsis
Amazon Simple Email Service (SES) is a high-scale, cost-effective platform for sending transactional, marketing, and notification emails. For agents, SES serves as the primary outbound communication bridge to human users or other services. It is deeply integrated into the AWS ecosystem, offering superior governance through IAM and high reliability. While it offers a generous free tier (3,000 messages per month for 12 months for new accounts), it is notoriously "agent-hostile" during initial setup due to its strict "Sandbox" mode, which restricts sending to verified addresses only until a human manually requests a limit increase. Once out of the sandbox, its programmatic scalability and low cost ($0.10 per 1,000 emails) make it a top-tier choice for high-volume agentic workflows.

---

## 2. Connection Methods

### REST API
Amazon SES provides a Query API (HTTPS) that follows standard AWS signature version 4 (SigV4) signing. While direct REST calls are possible, they are cumbersome for agents to implement from scratch due to the complex signing process.

### SDKs
This is the preferred connection method. AWS provides mature, well-documented SDKs for all major languages.
- **Python:** `boto3` (The industry standard for AWS automation).
- **JavaScript/TypeScript:** `@aws-sdk/client-ses` (Modular v3 SDK).
- **Go/Java/Rust:** Official AWS SDKs are available for all.
Agents benefit from the SDKs' built-in retry logic and structured error types.

### MCP (Model Context Protocol)
There is no official AWS-maintained MCP server for SES. However, many developers use the `aws-mcp` community wrappers or define custom tools that wrap `boto3` calls, allowing LLMs to invoke email sending as a standard tool.

### Webhooks
SES does not send webhooks directly. Instead, it publishes events (bounces, complaints, deliveries) to **Amazon SNS (Simple Notification Service)**. Agents must subscribe to an SNS topic or an SQS queue to receive and process these asynchronous feedback loops.

### Auth Flows
Authentication is handled via **AWS IAM (Identity and Access Management)**.
- **Long-lived:** IAM User Access Key/Secret Key.
- **Temporary:** IAM Roles (via STS), which is the recommended approach for agents running on EC2, Lambda, or ECS to avoid credential leakage.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| `SendEmail` | `ses:SendEmail` | Sends a basic formatted email (HTML/Text). |
| `SendRawEmail` | `ses:SendRawEmail` | Sends MIME-formatted email; required for attachments. |
| `SendTemplatedEmail` | `ses:SendTemplatedEmail` | Injects JSON data into a pre-defined SES template. |
| `VerifyEmailIdentity` | `ses:VerifyEmailIdentity` | Starts the verification process for a sender email or domain. |
| `GetSendQuota` | `ses:GetSendQuota` | Returns the agent's current 24-hour sending limit and rate. |
| `GetSendStatistics` | `ses:GetSendStatistics` | Returns metrics on bounces, complaints, and deliveries. |
| `CreateEmailTemplate` | `ses:CreateEmailTemplate` | Programmatically defines a reusable email layout. |

---

## 4. Setup Guide

### For Humans
1. **AWS Account:** Sign in to the AWS Management Console.
2. **Verify Identity:** Navigate to SES > Verified Identities. Add a domain or email address.
3. **DNS Configuration:** If verifying a domain, add the provided CNAME records to your DNS provider (DKIM).
4. **Request Production Access:** **CRITICAL.** By default, you are in the Sandbox. You must open a support case to "Request Account Details" to move to production. This requires a human to describe the use case.
5. **IAM User:** Create an IAM user with `ses:SendEmail` permissions and save the credentials.

### For Agents
Agents must validate that the environment is "ready to send" before attempting high-volume tasks.
1. **Check Identity Status:** Ensure the `Source` email is verified.
2. **Check Sandbox Status:** Check if the account is still restricted.
3. **Verify Quota:** Ensure `Max24HourSend` is sufficient for the task.

```python
import boto3

ses = boto3.client('ses', region_name='us-east-1')

def validate_connection():
    # Check if we are out of the sandbox / check limits
    quota = ses.get_send_quota()
    print(f"Max 24h Send: {quota['Max24HourSend']}")
    
    # Check if our sender identity is verified
    identities = ses.list_identities(IdentityType='EmailAddress')
    return "authorized_email@example.com" in identities['Identities']
```

---

## 5. Integration Example

```python
import boto3
from botocore.exceptions import ClientError

def agent_send_notification(recipient, subject, body_text):
    client = boto3.client('ses', region_name='us-east-1')
    
    try:
        response = client.send_email(
            Destination={'ToAddresses': [recipient]},
            Message={
                'Body': {'Text': {'Charset': "UTF-8", 'Data': body_text}},
                'Subject': {'Charset': "UTF-8", 'Data': subject},
            },
            Source="agent@verified-domain.com",
            # ConfigurationSetName='ConfigSet' # Optional: for tracking
        )
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'MessageRejected':
            print("Agent Action: Email rejected. Check if recipient is suppressed.")
        elif error_code == 'Throttling':
            print("Agent Action: Rate limit hit. Backing off.")
        else:
            raise e
    else:
        return response['MessageId']
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 180ms | Fast for transactional triggers. |
| **P95 Latency** | 420ms | Occasional spikes during AWS region congestion. |
| **P99 Latency** | 750ms | Rare, usually related to large MIME payloads. |
| **Rate Limit** | Variable | Starts at 1 email/sec (Sandbox) to 100s/sec (Prod). |
| **Max Payload** | 10 MB | Includes attachments and headers. |

---

## 7. Agent-Native Notes

*   **Idempotency:** SES does **not** natively support idempotency tokens on the `SendEmail` API. Agents must implement a local "sent" database or use unique `Message-ID` tracking in logs to prevent duplicate sends during retries.
*   **Retry Behavior:** The AWS SDKs automatically retry on `5xx` errors and `Throttling` (400). Agents should catch `ThrottlingException` and implement a "sleep and retry" loop if the SDK's internal retry count is exhausted.
*   **Error Codes → Agent Decisions:** 
    *   `AccountSendingPaused`: Escalation required; the agent cannot fix this. 
    *   `MessageRejected`: Likely a blacklist or unverified address in Sandbox; agent should log and skip.
    *   `LimitExceededException`: Agent should pause operations for the current 24-hour window.
*   **Schema Stability:** AWS SES APIs are exceptionally stable. Changes are additive and rarely break existing integrations, making it safe for long-term agent autonomy.
*   **Cost-per-operation:** Extremely low. At $0.10 per 1,000 emails, an agent can send 10,000 emails for $1.00, making it one of the few services where API cost is negligible compared to compute cost.
*   **Suppression List:** SES maintains a managed suppression list. If an agent tries to send to an address that recently bounced, SES will block the request. Agents should query the suppression list API to clean their own contact lists.
*   **Sandbox Friction:** The Sandbox is the primary barrier for autonomous agents. An agent cannot "self-promote" to production; it requires a human to interact with AWS Support.

---

## 8. Rhumb Context: Why Amazon SES Scores 5.84 (L3)

Amazon SES's **5.84 score** reflects a service that is technically robust but burdened by legacy "anti-spam" friction that hinders immediate agent autonomy:

1. **Execution Autonomy (7.2)** — The AWS SDKs are world-class. They provide structured, typed responses that agents can easily parse. The `SendTemplatedEmail` primitive allows agents to separate logic (data) from presentation (HTML), reducing the token overhead of passing large HTML strings through an LLM.

2. **Access Readiness (4.0)** — This is the service's weakest point. The "Sandbox" mode is a significant hurdle for autonomous deployment. While an agent can programmatically verify an email, it cannot programmatically request the removal of sending limits, requiring human intervention for the most critical step of the setup.

3. **Agent Autonomy (6.67)** — SES excels in governance and auditability. Through IAM, an agent can be restricted to *only* sending from a specific address, minimizing the blast radius of a compromised key. Integration with SNS/SQS allows agents to build sophisticated "self-healing" loops where they automatically remove bouncing emails from their database without human oversight.

**Bottom line:** Amazon SES is the "Enterprise Grade" choice for agents. It is the most cost-effective and secure option, but it requires a human to "bless" the account before the agent can truly take flight. For developers who prioritize governance and low unit costs over instant setup, SES is the L3 standard.

**Competitor context:** **SendGrid (6.8)** and **Resend (7.4)** score higher on Access Readiness because they allow agents to start sending to external addresses immediately upon account creation. However, **SES** wins on Governance (9.0) compared to Resend's simpler API key model. For agents operating within the AWS ecosystem, SES remains the logical choice despite the setup friction.
