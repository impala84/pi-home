'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {loadArtistProfile, playingMetadata, chooseItem, artistCandidates, chooseMusicBrainzGroup, chooseUniqueTitleGroup, musicBrainzFacts, parseBandcampPage, loadAlbumWriteup, loadMusicBrainzMetadata, loadDetails} = require('./details-state');

test('artist background follows only a unique exact MusicBrainz identity', async () => {
  const id = '12345678-1234-1234-1234-123456789abc';
  const calls = [];
  const json = async path => {
    calls.push(path);
    return path.includes('?query=') ? {artists:[{name:'Radiohead',id}]} : {relations:[{url:{resource:'https://en.wikipedia.org/wiki/Radiohead'}}]};
  };
  const result = await loadArtistProfile('Radiohead', json, async()=>JSON.stringify({extract:'A British rock band.'}));
  assert.equal(result.writeup, 'A British rock band.'); assert.equal(result.source,'Wikipedia');
  assert.match(calls[1], /inc=url-rels/);
  for (const artists of [[{name:'Other',id}], [{name:'Radiohead',id},{name:'Radiohead',id}]]) {
    const result = await loadArtistProfile('Radiohead', async()=>({artists}), async()=>{throw Error('Must not request a biography')});
    assert.equal(result.writeup,'');
  }
});

test('playingMetadata reads three-line Roon metadata', () => {
  assert.deepEqual(playingMetadata({now_playing: {three_line: {line1: 'Track', line2: 'Artist', line3: 'Album'}, image_key: 'art'}}),
    {track: 'Track', artist: 'Artist', album: 'Album', image_key: 'art', key: 'artist|album'});
});

test('artist biography resolves the identity-linked Wikidata article', async () => {
  const id = '12345678-1234-1234-1234-123456789abc';
  const result = await loadArtistProfile('Radiohead', async path=>path.includes('?query=')?{artists:[{name:'Radiohead',id}]}:{relations:[{url:{resource:'https://www.wikidata.org/wiki/Q44190'}}]},
    async url=>url.includes('Special:EntityData')?JSON.stringify({entities:{Q44190:{sitelinks:{enwiki:{title:'Radiohead'}}}}}):JSON.stringify({extract:'Radiohead biography.'}));
  assert.equal(result.writeup,'Radiohead biography.'); assert.equal(result.source,'Wikipedia');
});

test('chooseItem prefers an exact title and ignores headers', () => {
  const result = chooseItem([{title: 'Albums', item_key: 'header', hint: 'header'}, {title: 'Blue Train Deluxe', item_key: 'a'}, {title: 'Blue Train', item_key: 'b'}], 'Blue Train');
  assert.equal(result.item_key, 'b');
});

test('loadDetails sends search text directly and merges cached external facts', async () => {
  const sessions = new Map();
  const service = {
    browse(options, callback) {
      const session = sessions.get(options.multi_session_key) || {};
      if (options.pop_all) { assert.ok(options.input); assert.equal(options.item_key, undefined); }
      if (options.input) session.stage = options.input === 'Artist' ? 'artist-results' : 'album-results';
      else if (options.item_key === 'album') session.stage = 'tracks';
      sessions.set(options.multi_session_key, session); callback(false, {action: 'list', list: {count: 1}});
    },
    load(options, callback) {
      const stage = sessions.get(options.multi_session_key)?.stage;
      const items = !stage ? [{title: 'No Results'}]
        : stage === 'artist-results' ? [{title: 'Artist', item_key: 'artist', image_key: 'artist-art'}]
        : stage === 'album-results' ? [{title: 'Album', item_key: 'album', image_key: 'album-art', subtitle: '1999'}]
        : [{title: 'Track one', subtitle: '3:12'}];
      callback(false, {items});
    }
  };
  const enrich = async () => ({year: '1999', release_date: '1999-04-01', genres: ['Electronic'], type: 'Album', country: 'US', label: 'Example', format: 'CD', edition_count: 2, track_count: 1, source: 'MusicBrainz', writeup: 'A concise album story.', writeup_source: 'Wikipedia'});
  const result = await loadDetails(service, {zone_id: 'zone', now_playing: {three_line: {line1: 'Track one', line2: 'Artist', line3: 'Album'}, image_key: 'current'}}, enrich);
  assert.equal(result.artist_image_key, 'artist-art'); assert.equal(result.album_image_key, 'album-art'); assert.equal(result.subtitle, '1999'); assert.equal(result.tracks[0].title, 'Track one');
  assert.equal(result.metadata.year, '1999'); assert.deepEqual(result.metadata.genres, ['Electronic']);
  assert.equal(result.library_status, 'unknown');
});

test('library status is positive only when Roon exposes its remove action', async () => {
  const sessions = new Map();
  const service = {
    browse(options, callback) {
      const session = sessions.get(options.multi_session_key) || {};
      if (options.input) session.stage = options.input === 'Artist' ? 'artist-results' : 'album-results';
      else if (options.item_key === 'album') session.stage = 'album';
      sessions.set(options.multi_session_key, session); callback(false, {action:'list'});
    },
    load(options, callback) {
      const stage = sessions.get(options.multi_session_key)?.stage;
      callback(false, {items: stage === 'artist-results' ? [] : stage === 'album-results' ? [{title:'Album', item_key:'album'}]
        : stage === 'album' ? [{title:'Remove from Library', hint:'action', item_key:'remove'}, {title:'Track one'}] : []});
    }
  };
  const result = await loadDetails(service, {zone_id:'zone', now_playing:{three_line:{line1:'Track one',line2:'Artist',line3:'Album'}}}, async()=>({}));
  assert.equal(result.library_status, 'in_library');
});

test('album information still loads when both Roon searches fail', async () => {
  const service = {browse(_options, callback) { callback('Roon browse temporarily unavailable'); }};
  let enriched = false;
  const result = await loadDetails(service, {zone_id: 'zone', now_playing: {three_line: {line1: 'R U Mine?', line2: 'Arctic Monkeys', line3: 'AM'}}}, async (album, artist) => {
    assert.equal(album, 'AM'); assert.equal(artist, 'Arctic Monkeys'); enriched = true;
    return {year: '2013', track_count: 12, writeup: 'Album information', source: 'MusicBrainz'};
  });
  assert.equal(enriched, true); assert.equal(result.metadata.year, '2013'); assert.equal(result.metadata.track_count, 12);
});

test('temporary enrichment failure is marked for a bounded retry', async () => {
  const service = {browse(_options, callback) { callback('offline'); }};
  const result = await loadDetails(service, {zone_id: 'zone', now_playing: {three_line: {line1: 'Track', line2: 'Artist', line3: 'Album'}}}, async () => { throw new Error('temporary timeout'); });
  assert.equal(result.status, 'ready'); assert.equal(result.metadata_retryable, true);
});

test('MusicBrainz matching requires the exact album and artist', () => {
  const groups = [
    {id: 'wrong', title: 'Chrysalis Deluxe', score: 100, 'artist-credit': [{name: 'Someone Else'}]},
    {id: 'right', title: 'Chrysalis', score: 100, 'artist-credit': [{name: 'Emancipator'}]}
  ];
  assert.equal(chooseMusicBrainzGroup(groups, 'Chrysalis', 'Emancipator').id, 'right');
  assert.equal(chooseMusicBrainzGroup(groups, 'Unknown', 'Emancipator'), null);
});

test('MusicBrainz matching accepts the album artist within Roon track credits', () => {
  assert.deepEqual(artistCandidates('Emancipator / SunSquabi / Stephanie Starnes'), ['Emancipator', 'SunSquabi', 'Stephanie Starnes', 'Emancipator / SunSquabi / Stephanie Starnes']);
  const groups = [{id: 'chrysalis', title: 'Chrysalis', score: 100, 'artist-credit': [{name: 'Emancipator'}]}];
  assert.equal(chooseMusicBrainzGroup(groups, 'Chrysalis', 'Emancipator / SunSquabi / Stephanie Starnes').id, 'chrysalis');
});

test('MusicBrainz title fallback accepts only one exact album title', () => {
  const unique = [{id: 'exact', title: 'Edits by Mr. K'}, {id: 'other', title: 'Danny Krivit: Edits by Mr. K'}];
  assert.equal(chooseUniqueTitleGroup(unique, 'Edits by Mr. K').id, 'exact');
  assert.equal(chooseUniqueTitleGroup([...unique, {id: 'ambiguous', title: 'Edits by Mr. K'}], 'Edits by Mr. K'), null);
});

test('MusicBrainz enrichment falls back to a unique exact album title', async () => {
  const paths = [];
  const fetchJson = async path => {
    paths.push(path);
    if (path.includes('/fallback?')) return {id: 'fallback', title: 'Edits by Mr. K', 'first-release-date': '2019-11-01', 'primary-type': 'EP', genres: [{name: 'electronic', count: 1}], releases: []};
    if (path.includes('query=') && path.includes('limit=10')) return {'release-groups': [{id: 'fallback', title: 'Edits by Mr. K'}, {id: 'other', title: 'Different Album'}]};
    return {'release-groups': []};
  };
  const facts = await loadMusicBrainzMetadata('Edits by Mr. K', 'The Vision / Andreya Triana', 0, fetchJson);
  assert.equal(facts.year, '2019'); assert.equal(facts.type, 'EP'); assert.equal(facts.genres[0], 'electronic');
  assert(paths.some(path => path.includes('limit=10')));
});

test('MusicBrainz facts expose useful compact album metadata', () => {
  const facts = musicBrainzFacts({
    'first-release-date': '2011-11-21', 'primary-type': 'Album', 'secondary-types': ['Remix'],
    genres: [{name: 'Downtempo', count: 9}, {name: 'Electronic', count: 4}],
    releases: [{status: 'Official', date: '2011-11-21', country: 'US'}, {status: 'Official', date: '2012', country: 'GB'}]
  }, 12);
  assert.deepEqual(facts, {release_date: '2011-11-21', year: '2011', genres: ['Downtempo', 'Electronic'], type: 'Album · Remix', country: 'United States', label: '', format: '', edition_count: 2, track_count: 12, source: 'MusicBrainz'});
});

test('MusicBrainz enrichment performs a search then a structured lookup', async () => {
  const paths = [];
  const fetchJson = async path => {
    paths.push(path);
    return paths.length === 1 ? {'release-groups': [{id: 'abc', title: 'Album', score: 100, 'artist-credit': [{name: 'Artist'}]}]}
      : {id: 'abc', title: 'Album', 'first-release-date': '2004', 'primary-type': 'Album', genres: [{name: 'Ambient', count: 3}], releases: []};
  };
  const facts = await loadMusicBrainzMetadata('Album', 'Artist', 8, fetchJson);
  assert.equal(paths.length, 2); assert.match(paths[0], /release-group/); assert.match(paths[1], /\/abc\?/);
  assert.equal(facts.year, '2004'); assert.equal(facts.track_count, 8);
});

test('Bandcamp parsing returns artist notes and a small tag set', () => {
  const page = '<div class="tralbumData tralbum-about">A story &amp; some <b>context</b>.</div><a class="tag">electronic</a><a class="tag">downtempo</a>';
  assert.deepEqual(parseBandcampPage(page), {writeup: 'A story & some context.', tags: ['electronic', 'downtempo']});
});

test('album writeup prefers a linked Wikipedia summary', async () => {
  const group = {relations: [{url: {resource: 'https://en.wikipedia.org/wiki/Example_album'}}]};
  const result = await loadAlbumWriteup(group, null, async () => JSON.stringify({type: 'standard', extract: 'The album story.'}));
  assert.deepEqual(result, {writeup: 'The album story.', source: 'Wikipedia', tags: []});
});
