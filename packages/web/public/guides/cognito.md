# Amazon Cognito — Agent-Native Service Guide

> **AN Score:** 5.32 · **Tier:** L2 · **Category:** Authentication & Identity

---

## 1. Synopsis
Amazon Cognito provides a robust, developer-centric framework for user authentication, authorization, and user management. For autonomous agents, Cognito serves two primary roles: acting as an identity provider for the agent's own users (User Pools) and exchanging third-party identities for temporary, privileged AWS credentials (Identity Pools). It is a critical bridge for agents that need to operate within the AWS ecosystem or manage secure sessions across distributed services. Cognito features a generous free tier, offering 50,000 monthly active users (MAUs) for standard users, making it highly cost-effective for agents in the prototyping and scaling phases. Its deep integration with AWS IAM makes it the go-to choice for agents requiring granular, policy-based access to cloud infrastructure.

---

## 2. Connection Methods

### REST API
Cognito exposes a set of regional endpoints (e.g., `cognito-idp.us-east-1.amazonaws.com`). All requests must be signed using AWS Signature Version 4 (SigV4). While direct REST calls are possible, the complexity of calculating signatures and handling SRP (Secure Remote Password) protocols manually makes this path inefficient for agents compared to SDKs.

### SDKs
Cognito is natively supported by all official AWS SDKs. For agents, the most relevant are:
*   **Python:** `boto3` (clients: `cognito-idp` for User Pools and `cognito-identity` for Identity Pools).
*   **JavaScript/TypeScript:** `@aws-sdk/client-cognito-identity-provider` and `@aws-sdk/client-cognito-identity`.
*   **Go:** `aws-sdk-go-v2/service/cognitoidentityprovider`.

### MCP
There is currently no official Model Context Protocol (MCP) server for Cognito, though agents can utilize the AWS CLI MCP wrapper to execute Cognito commands if the environment is pre-configured with the necessary IAM permissions.

### Webhooks
Cognito uses "Lambda Triggers" instead of standard outbound webhooks. Agents can be notified of events (Post-confirmation, Pre-token generation, etc.) by associating an AWS Lambda function with specific User Pool events. This allows agents to trigger side effects, like provisioning database records, immediately after a user authenticates.

### Auth Flows
Agents typically use the `ADMIN_NO_SRP_AUTH` flow for backend-to-backend authentication or `USER_PASSWORD_AUTH` for simulating user logins. For long-running agents, `REFRESH_TOKEN_AUTH` is essential to maintain session persistence without re-storing sensitive credentials.

---

## 3. Key Primitives

| Primitive | Endpoint/Method | Description |
| :--- | :--- | :--- |
| **AdminCreateUser** | `AdminCreateUser` | Programmatically creates a user without requiring an email invitation. |
| **AdminInitiateAuth** | `AdminInitiateAuth` | Authenticates a user as an administrator; returns ID, Access, and Refresh tokens. |
| **GetId** | `GetId` | Generates a unique identifier in an Identity Pool for a user. |
| **GetCredentials** | `GetCredentialsForIdentity` | Exchanges an identity ID for temporary AWS credentials (AccessKey, SecretKey, SessionToken). |
| **SignUp** | `SignUp` | Public endpoint for self-service user registration. |
| **RespondToAuthChallenge** | `RespondToAuthChallenge` | Handles MFA, New Password Required, and other auth state transitions. |
| **GetUser** | `GetUser` | Retrieves attributes for the currently authenticated user using an Access Token. |

---

## 4. Setup Guide

### For Humans
1.  Log into the **AWS Management Console** and navigate to **Amazon Cognito**.
2.  Click **Create user pool** and configure your sign-in options (Email, Username, etc.).
3.  Under **App clients**, create a new client. For backend agents, ensure "Generate client secret" is checked.
4.  Note your **User Pool ID** (e.g., `us-east-1_abcd123`) and **Client ID**.
5.  If using Identity Pools, navigate to **Identity pools**, create a new pool, and link it to your User Pool ID and Client ID.
6.  Assign an **IAM Role** to the Identity Pool to define what AWS resources the agent/user can access.

### For Agents
1.  **Credential Discovery:** Ensure the agent has `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` with `cognito-idp:*` permissions.
2.  **Environment Sync:** Inject `USER_POOL_ID` and `CLIENT_ID` into the agent's environment variables.
3.  **Connection Validation:** The agent should run a `describe_user_pool` call to verify connectivity.
4.  **Flow Verification:** Execute a test `admin_initiate_auth` to ensure the App Client configuration supports the intended auth flow.

```python
import boto3
client = boto3.client('cognito-idp', region_name='us-east-1')
# Validation check
response = client.describe_user_pool(UserPoolId='us-east-1_xxxxxx')
print(f"Connected to User Pool: {response['UserPool']['Name']}")
```

---

## 5. Integration Example

This Python example demonstrates an agent programmatically authenticating a user to retrieve tokens.

```python
import boto3

def get_agent_tokens(user_pool_id, client_id, username, password):
    client = boto3.client('cognito-idp')
    
    try:
        response = client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow='ADMIN_NO_SRP_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        
        # Extract tokens for subsequent API calls
        tokens = {
            'AccessToken': response['AuthenticationResult']['AccessToken'],
            'IdToken': response['AuthenticationResult']['IdToken'],
            'RefreshToken': response['AuthenticationResult']['RefreshToken']
        }
        return tokens

    except client.exceptions.NotAuthorizedException:
        return "Error: Invalid credentials."
    except client.exceptions.UserNotFoundException:
        return "Error: User does not exist."
    except Exception as e:
        return f"Unexpected error: {str(e)}"

# Usage
# tokens = get_agent_tokens('us-east-1_XYZ', 'client_id_123', 'agent_001', 'SecurePass123!')
```

---

## 6. Performance Characteristics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **P50 Latency** | 200ms | Standard authentication and token verification. |
| **P95 Latency** | 460ms | Observed during cross-region requests or high-load periods. |
| **P99 Latency** | 800ms | Usually involves complex Lambda triggers or MFA SMS delivery. |
| **Rate Limits** | 120-2,000 RPS | Varies by API (e.g., `AdminInitiateAuth` is higher than `CreateUserPool`). |
| **Cold Starts** | Minimal | As a managed service, Cognito has no significant cold start, but associated Lambda triggers do. |

---

## 7. Agent-Native Notes

*   **Idempotency:** Cognito does not support idempotency tokens for user creation. Agents must handle `UsernameExistsException` and `AliasExistsException` as "success" states if the goal is to ensure a user exists.
*   **Retry Behavior:** The AWS SDKs provide default retry logic for `LimitExceededException` (400) and `InternalErrorException` (500). Agents should be configured with `max_attempts=5` to handle transient throttling.
*   **Error Codes → Agent Decisions:**
    *   `PasswordResetRequiredException`: Agent must trigger a `ForgotPassword` flow or escalate to a human.
    *   `UserNotConfirmedException`: Agent should check if it needs to re-send a confirmation code.
    *   `NotAuthorizedException`: Immediate halt; signifies invalid credentials or a locked account.
*   **Schema Stability:** User Pool attributes are highly stable. However, custom attributes cannot be deleted once added, only hidden. Agents should treat the schema as append-only.
*   **Cost-per-operation:** Authentication calls are effectively free within the 50k MAU tier. Beyond the tier, costs are ~$0.0055 per MAU, making it one of the cheapest identity providers for high-volume agents.
*   **Token Refresh:** Agents should implement a background loop to refresh tokens using the `RefreshToken` before the `AccessToken` expires (typically 60 minutes) to avoid workflow interruption.
*   **Multi-Region Strategy:** Cognito User Pools are regional. For global agents, consider using **Cognito User Pool Global Tables** (limited availability) or manual synchronization logic.

---

## 8. Rhumb Context: Why Amazon Cognito Scores 5.32 (L2)

Cognito’s **5.32 score** reflects its status as a powerful but "heavy" infrastructure component that requires significant setup before an agent can operate autonomously:

1.  **Execution Autonomy (6.3)** — Cognito provides deep programmatic control over every stage of the identity lifecycle. The ability to switch between SRP and non-SRP flows allows agents to optimize for security or simplicity. However, the complexity of managing "Auth Challenges" (MFA, password resets) creates a state machine that is difficult for simpler agents to navigate without specific branching logic.

2.  **Access Readiness (3.7)** — This is Cognito's weakest dimension. Bootstrapping a Cognito-enabled agent requires navigating the AWS IAM console, creating User Pools, and configuring App Clients. It is not a "one-click" setup. Unlike Auth0 or Firebase, the barrier to entry for an agent to "self-provision" a secure identity layer is high due to the complexity of AWS permissions.

3.  **Agent Autonomy (6.67)** — Once configured, Cognito is exceptionally reliable. It integrates perfectly with AWS CloudTrail for governance, allowing a "supervisor" agent to audit exactly what identities the "worker" agent is creating or using. The usage-based pricing (per MAU) means agents can scale their user base without immediate financial friction.

**Bottom line:** Amazon Cognito is an L2 service because it is an "infrastructure-first" identity provider. It is the best choice for agents already living in the AWS ecosystem who need SOC2/ISO-compliant identity management, but it lacks the "agent-first" simplicity of newer, lighter auth providers.

**Competitor context:** **Auth0 (7.1)** scores higher due to better documentation and a more intuitive management API for agents. **Firebase Auth (6.8)** is preferred for agents needing simpler, cross-platform identity with lower configuration overhead. Cognito remains the superior choice only when deep **AWS IAM** integration is a hard requirement.
