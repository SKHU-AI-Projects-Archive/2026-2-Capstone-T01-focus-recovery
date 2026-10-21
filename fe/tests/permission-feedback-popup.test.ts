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
    permissions: { contains: vi.fn(async () => false), request: vi.fn(async () => false) },
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
// Lifecycle checks still use mock Chrome APIs; the native dialog is verified separately.
describe('optional site permission Popup adapter (mock Chrome API, not a native dialog)', () => {
  it('shows current missing permission and recovery instructions after closing during the native request', async () => {
    let denied!: (granted: boolean) => void;
    chromeApi.permissions.request.mockImplementationOnce(() => new Promise(resolve => { denied = resolve; }));
    await allow();
    await vi.waitFor(() => expect(chromeApi.permissions.request).toHaveBeenCalledTimes(1));
    root!.unmount(); root = undefined;
    denied(false);
    vi.resetModules(); await import('../src/popup/index');
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toContain('현재 사이트 접근 권한: 허용되지 않음'));
    expect(document.body.textContent).toContain('수집하려면 ‘현재 사이트 수집 허용’을 눌러 주세요.');
    expect(chromeApi.permissions.contains).toHaveBeenCalledWith({ origins: ['https://example.com/*'] });
    expect(chromeApi.runtime.sendMessage).not.toHaveBeenCalledWith({ type: 'sync-permissions' });
    expect(document.body.textContent).not.toContain('source=public');
  });
  it('reads the newly active site on reopen rather than retaining the previous denial', async () => {
    await allow();
    await vi.waitFor(() => expect(document.body.textContent).toContain('사이트 수집 권한이 허용되지 않았습니다.'));
    root!.unmount(); root = undefined;
    chromeApi.tabs.query.mockResolvedValue([{ url: 'https://another.example/docs?private=PRIVATE_QUERY#body' }]);
    chromeApi.permissions.contains.mockResolvedValue(true);
    vi.resetModules(); await import('../src/popup/index');
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toBe('현재 사이트 접근 권한: 허용됨'));
    expect(chromeApi.permissions.contains).toHaveBeenLastCalledWith({ origins: ['https://another.example/*'] });
    expect(chromeApi.permissions.request).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).not.toContain('사이트 수집 권한이 허용되지 않았습니다.');
    expect(document.body.textContent).not.toContain('PRIVATE_QUERY');
    expect(document.body.textContent).not.toContain('another.example');
  });
  it.each([false, true])('keeps the actual request result %s when the initial permission read finishes late', async granted => {
    let finish!: (value: boolean) => void;
    chromeApi.permissions.contains.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    chromeApi.permissions.request.mockResolvedValue(granted);
    await allow();
    const expected = `현재 사이트 접근 권한: ${granted ? '허용됨' : '허용되지 않음'}`;
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toBe(expected));
    finish(!granted); await new Promise(resolve => setTimeout(resolve, 20));
    expect(document.querySelector('[role="status"]')?.textContent).toBe(expected);
  });
  it.each(['chrome://extensions', undefined])('keeps unsupported or unavailable tab URLs unknown (%s)', async url => {
    chromeApi.tabs.query.mockResolvedValue([{ url }]);
    await import('../src/popup/index');
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toContain('현재 사이트 접근 권한을 확인할 수 없습니다.'));
    expect(chromeApi.permissions.contains).not.toHaveBeenCalled();
    expect(chromeApi.permissions.request).not.toHaveBeenCalled();
  });
  it('never reports a failed permission lookup as a denial or exposes the raw failure', async () => {
    chromeApi.permissions.contains.mockRejectedValue(Error('PRIVATE_PERMISSION_LOOKUP'));
    await import('../src/popup/index');
    await vi.waitFor(() => expect(document.querySelector('[role="status"]')?.textContent).toContain('현재 사이트 접근 권한을 확인할 수 없습니다.'));
    expect(document.body.textContent).not.toContain('PRIVATE_PERMISSION_LOOKUP');
    expect(document.body.textContent).not.toContain('현재 사이트 접근 권한: 허용되지 않음');
    expect(chromeApi.permissions.request).not.toHaveBeenCalled();
  });
  it('does not display raw permission failures or synchronize after rejection', async () => {
    chromeApi.permissions.request.mockRejectedValue(Error('PRIVATE_PERMISSION_ERROR'));
    await allow();
    await vi.waitFor(() => expect(document.body.textContent).toContain('일반 HTTP(S) 페이지에서 확장 프로그램을 열어 주세요.'));
    expect(document.body.textContent).not.toContain('PRIVATE_PERMISSION_ERROR');
    expect(document.querySelector('[role="status"]')?.textContent).toContain('현재 사이트 접근 권한을 확인할 수 없습니다.');
    expect(chromeApi.runtime.sendMessage).not.toHaveBeenCalledWith({ type: 'sync-permissions' });
  });
});
