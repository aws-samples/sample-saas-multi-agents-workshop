export const handler = async (event: any, context: any) => {
  const toolName = context.clientContext?.custom?.bedrockAgentCoreToolName;

  if (toolName.includes("search_kb")) {
    return {
      statusCode: 500,
      body: JSON.stringify({
        message:
          "Can't connect to Knowledge Base. Contact your administrator for guidance.",
      }),
    };
  } else {
    return {
      statusCode: 400,
      body: JSON.stringify({ message: "Unknown tool" }),
    };
  }
};
