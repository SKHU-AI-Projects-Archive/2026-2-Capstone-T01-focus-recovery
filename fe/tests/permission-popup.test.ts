// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DevStatus } from '../src/shared/types';

let root: { unmount(): void } | undefined;
let chromeApi: any;
beforeEach(() => {
  vi.resetModules();
  document.body.innerHTML = '<div id="root"></div>';
  vi.doMock('react-dom/client', async () => {
    const actual = await vi.importActual<typeof import('react-dom/client')>('react-dom/client');
    return { ...actual, createRoot: (...args: Parameters<typeof actual.createRoot>) => {
      root = actual.createRoot(...args); return root;
    } };
  });
  const status: DevStatus = { session: null, candidates: [], visits: [], readyVisits: [], capacityReached: false,
    storage: { phase: 'ready', recovered: false }, sessionStartRecovery: { kind: 'none' } };
  chromeApi = {
    runtime: { sendMessage: vi.fn(async () => ({ ok: true, status })) },
    tabs: { query: vi.fn(async () => [{ url: 'https://example.com/docs?source=public#body' }]) },
    permissions: { request: vi.fn(async () => false) },
  };
  vi.stubGlobal('chrome', chromeApi);
});
afterEach(() => { root?.unmount(); root = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks(); });
async function allow() {
  await import('../src/popup/index');
  const button = () => [...document.querySelectorAll('button')].find(b => b.textContent === '현재 사이트 수집 허용')!;
  await vi.waitFor(() => expect(button()?.disabled).toBe(false));
  button().click();
}
describe('optional site permission Popup adapter (mock Chrome API, not a native dialog)', () => {
  it('shows denial and does not synchronize collection permission', async () => {
    await allow();
    await vi.waitFor(() => expect(document.body.textContent).toContain('사이트 수집 권한이 허용되지 않았습니다.'));
    expect(chromeApi.permissions.request).toHaveBeenCalledWith({ origins: ['https://example.com/*'] });
    expect(chromeApi.runtime.sendMessage).not.toHaveBeenCalledWith({ type: 'sync-permissions' });
  });
  it('synchronizes only after Chrome grants the requested origin', async () => {
    chromeApi.permissions.request.mockResolvedValue(true);
    await allow();
    await vi.waitFor(() => expect(chromeApi.runtime.sendMessage).toHaveBeenCalledWith({ type: 'sync-permissions' }));
    expect(chromeApi.permissions.request).toHaveBeenCalledTimes(1);
  });
  it('does not display raw permission failures or synchronize after rejection', async () => {
    chromeApi.permissions.request.mockRejectedValue(Error('PRIVATE_PERMISSION_ERROR'));
    await allow();
    await vi.waitFor(() => expect(document.body.textContent).toContain('일반 HTTP(S) 페이지에서 확장 프로그램을 열어 주세요.'));
    expect(document.body.textContent).not.toContain('PRIVATE_PERMISSION_ERROR');
    expect(chromeApi.runtime.sendMessage).not.toHaveBeenCalledWith({ type: 'sync-permissions' });
  });
});
