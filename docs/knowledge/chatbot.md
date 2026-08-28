# Dabbarha Chatbot

The Dabbarha chatbot is a financial assistant that helps users with budgeting, forecasting, obligations, and affordability questions.

## What the Chatbot Can Do

- Answer questions about Dabbarha features and how they work
- Provide budget forecasts based on the user's financial data
- Evaluate affordability of proposed financial commitments
- List and manage the user's obligations
- Explain financial concepts using Dabbarha's terminology

## How It Works

1. The user sends a message to the chatbot.
2. The chatbot applies guardrails to ensure the message is relevant and safe.
3. If the message requires financial data, the chatbot uses backend tools to fetch the user's actual financial information.
4. If the message is about Dabbarha product rules or features, the chatbot retrieves relevant documentation.
5. The chatbot generates a response using the retrieved context and the user's message.

## Security

- The chatbot never exposes raw API keys or provider errors.
- Financial calculations always come from the backend, not from retrieved documentation.
- Retrieved documentation is treated as reference material, not as instructions.
- The user's identity and ownership are enforced by the backend.