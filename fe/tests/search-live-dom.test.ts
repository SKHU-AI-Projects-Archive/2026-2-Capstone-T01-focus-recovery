// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { extractSearchContent } from '../src/content/search';
import { inspectUrl, normalizeUrl } from '../src/shared/url';

// Opt in to reproduce the unresolved product defect without weakening its expectation.
// See docs/real-search-permission-e2e-validation.md; a skipped case is never a PASS.
describe.skipIf(process.env.RUN_KNOWN_SEARCH_BUG !== '1')('observed Naver DOM: unresolved collection defect', () => {
  it.each(['Spring Boot JWT', '스프링 부트 인증'])('collects ordinary web results for %s', query => {
    document.documentElement.innerHTML = readFileSync('tests/fixtures/naver-20261019.html', 'utf8');
    const raw = `https://search.naver.com/search.naver?query=${encodeURIComponent(query)}&where=nexearch#results`;
    expect(inspectUrl(raw)).toMatchObject({ searchQuery: query, isSearchResultPage: true });
    expect(normalizeUrl(raw)).toBe('https://search.naver.com/search.naver');
    expect(extractSearchContent(document, raw)).toEqual({
      content: `검색어: ${query}\n\n검색 결과 1\n제목: 공개 인증 문서\n설명: 공개 검색 설명입니다.`,
      organicResultCount: 1,
    });
  });
});
