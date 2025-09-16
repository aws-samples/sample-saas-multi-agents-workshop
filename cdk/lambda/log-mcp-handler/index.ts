export const handler = async (event: any, context: any) => {
  const toolName = context.clientContext?.custom?.bedrockAgentCoreToolName;

  if (toolName.includes("search_logs")) {
    const logs = [];
    for (let day = 1; day <= 2; day++) {
      for (let hour = 0; hour < 20; hour++) {
        const minute = Math.floor(Math.random() * 60);
        const level = ["INFO", "WARN", "ERROR"][Math.floor(Math.random() * 3)];
        const service = ["frontend", "backend", "database"][
          Math.floor(Math.random() * 3)
        ];
        const podId = Math.floor(Math.random() * 9000) + 1000;
        const status = [
          "Started",
          "Stopped",
          "Restarted",
          "Scaled",
          "HealthCheck passed",
          "HealthCheck failed",
          "OOMKilled",
          "Completed",
          "NetworkTimeout",
        ][Math.floor(Math.random() * 9)];

        logs.push(
          `2024-04-${day.toString().padStart(2, "0")}T${hour
            .toString()
            .padStart(2, "0")}:${minute
            .toString()
            .padStart(
              2,
              "0"
            )}:00.000Z [eks-cluster] [${level}] Pod ${service}-${podId} ${status} in namespace production`
        );
      }
    }

    return {
      statusCode: 200,
      body: JSON.stringify({ log: logs }),
    };
  } else {
    return {
      statusCode: 200,
      body: JSON.stringify({ message: "Unknown tool" }),
    };
  }
};
