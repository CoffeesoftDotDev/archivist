import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { buildLaunch } from "./launch-mcp.mjs";

const valid = {
  ARCHIVIST_REVIEWED_COMMIT: "a".repeat(40),
  ARCHIVIST_SOURCE_ROOT: path.resolve("source with spaces"),
  ARCHIVIST_DESTINATION_ROOT: path.resolve("destination"),
};

test("launch uses a direct immutable source pin and separate explicit roots", () => {
  const launch = buildLaunch(valid);
  assert.equal(launch.command, "uvx");
  assert.deepEqual(launch.args, [
    "--from",
    `archivist[mcp] @ git+https://github.com/CoffeesoftDotDev/archivist.git@${"a".repeat(40)}`,
    "archivist-mcp", "--stdio",
    "--source-root", valid.ARCHIVIST_SOURCE_ROOT,
    "--destination-root", valid.ARCHIVIST_DESTINATION_ROOT,
  ]);
});

test("missing, placeholder, branch and abbreviated pins fail closed", () => {
  for (const pin of [
    undefined, "", "main", "abc123", "REPLACE_WITH_REVIEWED_FULL_40_HEX_SHA",
    `${"a".repeat(40)}\n`, `${"a".repeat(40)} --apply`,
  ]) {
    assert.throws(() => buildLaunch({ ...valid, ARCHIVIST_REVIEWED_COMMIT: pin }), /40-hex/);
  }
});

test("both roots must be explicit absolute paths", () => {
  for (const field of ["ARCHIVIST_SOURCE_ROOT", "ARCHIVIST_DESTINATION_ROOT"]) {
    const invalid = [undefined, "", "relative"];
    if (process.platform === "win32") invalid.push("\\photos", "C:photos");
    for (const value of invalid) {
      assert.throws(() => buildLaunch({ ...valid, [field]: value }), /absolute/);
    }
  }
});

test("startup configuration failures use stderr, never protocol stdout", () => {
  const result = spawnSync(process.execPath, [
    fileURLToPath(new URL("./launch-mcp.mjs", import.meta.url)),
  ], {
    env: { ...process.env, ARCHIVIST_REVIEWED_COMMIT: "" },
    encoding: "utf8",
  });
  assert.equal(result.status, 1);
  assert.equal(result.stdout, "");
  assert.match(result.stderr, /reviewed full 40-hex/);
});
