import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function buildLaunch(env) {
  const commit = env.ARCHIVIST_REVIEWED_COMMIT;
  if (typeof commit !== "string" || commit.length !== 40 || !/^[0-9a-fA-F]{40}$/.test(commit)) {
    throw new Error("ARCHIVIST_REVIEWED_COMMIT must be a reviewed full 40-hex server commit.");
  }
  const source = env.ARCHIVIST_SOURCE_ROOT;
  const destination = env.ARCHIVIST_DESTINATION_ROOT;
  for (const [name, value] of [
    ["ARCHIVIST_SOURCE_ROOT", source],
    ["ARCHIVIST_DESTINATION_ROOT", destination],
  ]) {
    if (!value || !path.isAbsolute(value)
        || (process.platform === "win32" && path.parse(value).root.length === 1)) {
      throw new Error(`${name} must be an explicit absolute directory path.`);
    }
  }
  return {
    command: "uvx",
    args: [
      "--from",
      `archivist[mcp] @ git+https://github.com/CoffeesoftDotDev/archivist.git@${commit}`,
      "archivist-mcp",
      "--stdio",
      "--source-root",
      source,
      "--destination-root",
      destination,
    ],
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const launch = buildLaunch(process.env);
    const child = spawn(launch.command, launch.args, {
      stdio: "inherit",
      shell: false,
    });
    child.on("error", (error) => {
      process.stderr.write(`Archivist launcher: ${error.message}\n`);
      process.exitCode = 1;
    });
    child.on("exit", (code) => {
      process.exitCode = code ?? 1;
    });
    for (const signal of ["SIGINT", "SIGTERM"]) {
      process.on(signal, () => child.kill(signal));
    }
  } catch (error) {
    process.stderr.write(`Archivist launcher: ${error.message}\n`);
    process.exitCode = 1;
  }
}
