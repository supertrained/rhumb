# Amazon Web Services — Agent-Native Service Guide

> **AN Score:** 5.72 · **Tier:** L2 · **Category:** Deployment & Hosting

---

## 1. Synopsis
Amazon Web Services (AWS) provides the world's most comprehensive cloud infrastructure, offering over 200 fully featured services from data centers globally. For agents, AWS is the "physical" layer of the internet, providing the compute (Lambda), storage (S3), and database (DynamoDB) primitives required to persist state and execute code. While its API surface is vast and its governance model (IAM) is the industry gold standard, the high barrier to entry and complex authentication make it a "Developing" (L2) agent-native service. The AWS Free Tier offers 12 months of limited usage for new accounts, plus "Always Free" tiers for services like Lambda (1M requests/month) and DynamoDB (25GB storage), making it accessible for agent prototyping.

---

## 2. Connection Methods

### REST API
AWS exposes virtually all functionality via RESTful APIs, but they are notoriously difficult for agents to call directly. Most services require **AWS Signature Version 4 (SigV4)**, a complex HMAC-based signing process for every request. Agents should avoid raw `fetch` or `requests` calls unless using a specialized signing library, as manual implementation of SigV4 is error-prone and brittle.

### SDKs
The primary and recommended way for agents to interact with AWS is through official SDKs. **Boto3 (Python)** and the **AWS SDK for JavaScript (v3)** are the most mature. These libraries handle SigV4 signing, request retries with exponential backoff, and XML/JSON parsing automatically. For agents, using the SDK reduces the "execution autonomy" friction significantly compared to raw API calls.

### MCP
There is currently no official AWS Model Context Protocol (MCP) server. However, the community has developed several wrappers that expose common AWS primitives (S3, Lambda, EC2) to LLMs. Agents typically access AWS through these tools or by writing and executing Python code that utilizes Boto3.

### Webhooks & Events
AWS does not use standard "webhooks" in the traditional SaaS sense. Instead, it uses **Amazon EventBridge** and **SNS/SQS**. Agents can subscribe to infrastructure changes (e.g., an S3 file upload or an EC2 instance state change) by configuring EventBridge rules to trigger a Lambda function or a public API endpoint that the agent monitors.

### Auth Flows
AWS uses **IAM (Identity and Access Management)**. For agents, the safest path is using **IAM Roles** with temporary credentials via the **Security Token Service (STS)**. Avoid hardcoding long-lived Access Keys. Agents operating within AWS (e.g., on EC2 or Lambda) should use Instance Profiles/Execution Roles to inherit permissions without needing explicit credentials.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **S3 Object** | `s3.put_object` | Stores unstructured data (logs, images, state) in buckets. |
| **Lambda Function** | `lambda.invoke` | Executes arbitrary code snippets in a serverless environment. |
| **DynamoDB Item** | `dynamodb.put_item` | Stores structured, NoSQL key-value pairs with sub-10ms latency. |
| **EC2 Instance** | `ec2.run_instances` | Provisions virtual machines for long-running agent processes. |
| **Bedrock Model** | `bedrock-runtime.invoke_model` | Accesses foundation models (Claude, Llama, Titan) via AWS API. |
| **SQS Message** | `sqs.send_message` | Queues tasks for asynchronous agent processing. |
| **Secrets Manager** | `secretsmanager.get_secret_value` | Securely retrieves API keys for other services. |

---

## 4. Setup Guide

### For Humans
1. Create an AWS Account at [portal.aws.amazon.com](https://portal.aws.amazon.com).
2. Set up a Credit Card (required even for the Free Tier).
3. Navigate to the **IAM Console** and create a new **IAM User**.
4. Attach a "Programmatic Access" policy (e.g., `AmazonS3FullAccess`) to the user.
5. Generate an **Access Key ID** and **Secret Access Key**.
6. Store these keys in a secure environment variable manager.
7. (Optional) Set up a Billing Alarm to prevent unexpected autonomous spending.

### For Agents
1. **Environment Setup**: Ensure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` are in the environment.
2. **Dependency Check**: Install the SDK (e.g., `pip install boto3`).
3. **Identity Validation**: Call `sts.get_caller_identity` to verify the agent's credentials and ARN.
4. **Permission Scoping**: Attempt a `list_buckets` or similar low-impact call to verify policy attachment.

```python
import boto3
from botocore.exceptions import ClientError

# Validation step for agents
def validate_connection():
    sts = boto3.client('sts')
    try:
        identity = sts.get_caller_identity()
        return f"Connected as: {identity['Arn']}"
    except ClientError as e:
        return f"Connection failed: {e}"
```

---

## 5. Integration Example

```python
import boto3
import json

# Initialize the S3 client
s3 = boto3.client('s3', region_name='us-east-1')

def save_agent_memory(bucket_name, session_id, memory_data):
    """
    Saves agent state to S3. 
    Demonstrates error handling and structured data storage.
    """
    try:
        response = s3.put_object(
            Bucket=bucket_name,
            Key=f"sessions/{session_id}.json",
            Body=json.dumps(memory_data),
            ContentType='application/json'
        )
        # Check for 200 OK
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return {"status": "success", "etag": response['ETag']}
    except s3.exceptions.NoSuchBucket:
        return {"status": "error", "message": "The specified bucket does not exist."}
    except ClientError as e:
        # Generic catch for IAM/Network issues
        return {"status": "error", "message": str(e)}

# Usage
memory = {"last_action": "created_ec2", "timestamp": "2023-10-27T10:00:00Z"}
print(save_agent_memory("my-agent-storage", "user-123", memory))
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 150ms | Typical for regional API calls (S3/DynamoDB). |
| **P95 Latency** | 350ms | Occurs during cold starts or cross-region requests. |
| **P99 Latency** | 600ms | High-load periods or complex IAM evaluations. |
| **Rate Limits** | Service-specific | DynamoDB uses RCUs/WCUs; Lambda has concurrency limits. |
| **Retry Safety** | High | SDKs include automatic retries for 5xx and throttling. |

---

## 7. Agent-Native Notes

*   **Idempotency**: AWS supports idempotency tokens (e.g., `ClientToken` in EC2, `ClientRequestToken` in Lambda) to prevent duplicate resource creation during retries.
*   **Retry behavior**: The SDKs default to "legacy" or "standard" retry modes. Agents should be configured to use `standard` or `adaptive` modes for better handling of throttling.
*   **Error codes**: AWS returns specific error strings (e.g., `ThrottlingException`, `AccessDeniedException`, `ResourceNotFoundException`). Agents should use these for branching logic rather than parsing error messages.
*   **Schema stability**: AWS has the highest schema stability in the industry. APIs are versioned by date (e.g., `2012-08-10`), and breaking changes are extremely rare.
*   **Cost-per-operation**: Costs are granular. A single `PutObject` call is ~$0.000005. Agents must be aware of "data transfer out" costs, which are often the hidden driver of AWS bills.
*   **IAM Granularity**: Agents can be restricted to specific "Resource ARNs," allowing an agent to only read from one specific S3 folder, minimizing blast radius.
*   **Global Footprint**: Agents can minimize latency by selecting the `AWS_REGION` closest to their execution environment or their end-users.

---

## 8. Rhumb Context: Why Amazon Web Services Scores 5.72 (L2)

AWS's **5.72 score** reflects a service that is technically peerless but architecturally hostile to autonomous agent onboarding:

1. **Execution Autonomy (7.1)** — Once connected, AWS is highly autonomous. The SDKs manage the heavy lifting of signing and retries. Features like `ClientRequestToken` allow agents to safely retry expensive operations (like launching a $100/hr GPU instance) without fear of duplication. The structured error codes allow for sophisticated agent recovery loops.

2. **Access Readiness (3.8)** — This is AWS’s primary weakness. The onboarding flow requires a credit card, identity verification, and a complex dance through the IAM console. An agent cannot "self-provision" an AWS account easily. The friction of setting up VPCs, subnets, and security groups just to run a simple script is a significant barrier compared to agent-native platforms like Vercel or Modal.

3. **Agent Autonomy (6.67)** — The **Governance Readiness (10)** is the highest possible, providing agents with the most secure environment available. IAM policies, CloudTrail auditing, and GuardDuty threat detection mean that an agent’s actions are fully traceable and restrictable. However, the **Payment Autonomy (7)** is complex; while usage-based, the billing console is difficult for an agent to navigate or programmatically "top up" without human intervention.

**Bottom line:** AWS is the "End Game" for agent infrastructure. It provides the most robust governance and scaling primitives, but the setup friction and steep learning curve for IAM make it a Tier-2 choice for rapid agent deployment. It is best suited for production-grade agents that require strict compliance and massive scale.

**Competitor context:** Google Cloud (5.4) and Azure (5.2) score similarly, suffering from the same "Enterprise Friction." In contrast, Vercel (7.8) and Railway (7.5) offer much higher Access Readiness for agents, though they lack the deep governance and service variety that keeps AWS at the top of the L2 tier.
