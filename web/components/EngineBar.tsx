"use client";

import { useEffect, useState } from "react";
import { engineStatus, onEngineStatus, type EngineStatus } from "@/lib/engine";

/** Slim progress bar while the engine loads. Editing works meanwhile: input is queued. */
export default function EngineBar() {
  const [status, setStatus] = useState<EngineStatus>(engineStatus());
  useEffect(() => onEngineStatus(setStatus), []);
  if (status.state === "ready") return null;
  if (status.state === "failed") {
    return (
      <div className="engine-bar failed" role="alert">
        The engine could not start: {status.error}. Try reloading; a recent Chrome, Safari or Firefox is needed.
      </div>
    );
  }
  return (
    <div className="engine-bar" role="progressbar" aria-label="Loading the engine" aria-valuemin={0}
      aria-valuemax={status.total} aria-valuenow={status.step} aria-valuetext={status.label}>
      <div className="engine-bar-fill" style={{ width: `${((status.step + 0.5) / status.total) * 100}%` }} />
      <span>{status.label}… you can start editing</span>
    </div>
  );
}

export function EngineVersion() {
  const [status, setStatus] = useState<EngineStatus>(engineStatus());
  useEffect(() => onEngineStatus(setStatus), []);
  return status.state === "ready" ? (
    <span>engine {status.version}</span>
  ) : (
    <span>engine loading</span>
  );
}
