/** @description Shared mutable application state with getter/setter functions. */

export const API = '';

export let currentSessionId = null;
export let currentSessionStatus = null;
export let currentEventSource = null;
export let streamingBubble = null;
export let fileTree = {};

export function setCurrentSessionId(v) { currentSessionId = v; }
export function setCurrentSessionStatus(v) { currentSessionStatus = v; }
export function setCurrentEventSource(v) { currentEventSource = v; }
export function setStreamingBubble(v) { streamingBubble = v; }
export function setFileTree(v) { fileTree = v; }
