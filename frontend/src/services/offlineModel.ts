/**
 * Generic fallback — Metro resolves offlineModel.native.ts on device
 * and offlineModel.web.ts on web. This file is never actually used at runtime
 * but satisfies TypeScript import resolution for non-platform-specific tooling.
 */
export * from './offlineModel.web';
