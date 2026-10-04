'use strict';

// Pure normalisation only. Importing this module cannot connect to a Core.
const {referencePreview} = require('../tools/discovery-wire.cjs');
function field(object, name) {
  const fields = object?.fields || object;
  return fields && Object.entries(fields).find(([key]) => key === name || key.endsWith(`::${name}`))?.[1];
}
function resolve(graph, value) {
  return value && typeof value === 'object' && '$ref' in value ? graph.getObject(BigInt(value.$ref)) : value;
}
function list(graph, value, limit = 5) {
  if (!Number.isSafeInteger(limit) || limit < 0 || limit > 20) throw new Error('Invalid discovery preview size');
  const object = resolve(graph, value);
  const items = field(object, '$items') ?? field(object, 'Items');
  const values = Buffer.isBuffer(items) ? referencePreview(items, limit) : Array.isArray(items) ? items.slice(0, limit) : [];
  return values.map(v => resolve(graph, v)).filter(v => v !== null && v !== undefined);
}
function text(value) {return String(value ?? '').replace(/\[\[\d+\|([^\]]+)\]\]/g, '$1').trim();}
function image(graph, value) {
  const object = resolve(graph, value);
  const url = field(object, 'Url');
  const id = field(object, 'ImageId');
  // These are private-protocol references, never official image_keys.
  return {url: typeof url === 'string' && /^(https:\/\/|broker:\/\/\/image\/)/.test(url) ? url : null, id: id == null ? null : String(id)};
}
function item(graph, value, kind = 'album') {
  const object = resolve(graph, value);
  if (!object) return null;
  const album = kind === 'track' ? resolve(graph, field(object, 'Album')) : object;
  const title = text(field(object, 'Title'));
  if (!title) return null;
  return {
    kind, title, artist: text(field(object, 'PerformedBy') || field(album, 'PerformedBy')),
    album: kind === 'track' ? text(field(album, 'Title')) : title,
    id: String(field(object, kind === 'track' ? 'TrackId' : 'AlbumId') ?? ''),
    roon_id: String(field(object, kind === 'track' ? 'RoonTrackId' : 'RoonAlbumId') ?? ''),
    release_id: String(field(object, 'RoonReleaseId') ?? ''),
    source: field(object, 'ContentSource') ?? field(object, 'Source') ?? null,
    artwork: image(graph, field(object, 'Image') || field(album, 'Image')),
  };
}
function mixes(graph, root, limit = 5) {
  return list(graph, root, limit).map(object => {
    const description = field(object, 'PerformerMixDescription') || field(object, 'GenreMixDescription');
    const artist = text(field(description, 'PerformerName'));
    const genre = text(field(description, 'GenreName'));
    const id = field(object, 'MixId');
    if (!Buffer.isBuffer(id) || !(artist || genre)) return null;
    const images = list(graph, field(description, 'Images'), 1);
    return {kind: 'mix', title: `${artist || genre} Mix`, artist, id: id.toString('hex'),
      description_type: text(field(object, 'DescriptionType')),
      context: list(graph, field(description, 'Touchstones')).map(text).filter(Boolean),
      artwork: image(graph, field(description, 'Avatar') || images[0]), object_ref: String(object.oid)};
  }).filter(Boolean);
}
function picks(graph, root, groupLimit = 3, itemLimit = 6) {
  return list(graph, root, groupLimit).map(box => {
    const seed = item(graph, field(box, 'SeedAlbum'));
    const id = field(box, 'ObjectId');
    return {kind: 'recommendation', id: Buffer.isBuffer(id) ? id.toString('hex') : '',
      reason: text(field(box, 'Reason')), category: text(field(box, 'OneBoxType')),
      generated_for: text(field(box, 'GeneratedForDate')), seed,
      items: list(graph, field(box, 'Albums'), itemLimit).map(v => item(graph, v)).filter(Boolean)};
  }).filter(box => box.items.length);
}
function recentAlbums(graph, events, limit = 20) {
  const normal = value => text(value).normalize('NFKC').toLocaleLowerCase();
  const seen = new Set(), result = [];
  const albums = [...graph.objects.values()].filter(object => /\.Album(?:Lite)?$/.test(object.typeName));
  const newest = [...events].sort((a,b) => (Date.parse(b.playedAt)||0) - (Date.parse(a.playedAt)||0));
  for (const event of newest) {
    const title = text(event.album), artist = text(event.artist);
    if (!title) continue;
    const identity = JSON.stringify([normal(title), normal(artist)]);
    if (seen.has(identity)) continue;
    seen.add(identity);
    const matches = albums.filter(album => normal(field(album,'Title')) === normal(title) && normal(field(album,'PerformedBy')) === normal(artist));
    const metadata = matches.length === 1 ? item(graph,matches[0],'album') : null;
    result.push({...metadata, kind:'album', title, album:title, artist, id:metadata?.id||'', playedAt:event.playedAt, artwork:metadata?.artwork||{url:null,id:null}});
    if (result.length >= limit) break;
  }
  return result;
}
module.exports = {field, resolve, list, text, image, item, mixes, picks, recentAlbums};
