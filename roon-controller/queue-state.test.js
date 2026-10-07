'use strict';
const {leadArtist, displayArtist} = require('./artist-name');

const assert = require('node:assert/strict');
const test = require('node:test');
const {queueItemsFromMessage, publicQueueItems, updateQueueState} = require('./queue-state');

test('keeps a subscribed queue in order and exposes compact display fields', () => {
  const raw = [
    {queue_item_id: 10, three_line: {line1: 'One', line2: 'Artist', line3: 'Album'}, length: 181, image_key: 'a'},
    {queue_item_id: 11, two_line: {line1: 'Two', line2: 'Another artist'}}
  ];
  const queue = publicQueueItems(queueItemsFromMessage('Subscribed', {items: raw}));
  assert.equal(queue.length, 2);
  assert.deepEqual(queue[0], {queue_item_id: 10, title: 'One', artist: 'Artist', album: 'Album', length: 181, image_key: 'a', is_current: true, is_previous: false});
  assert.equal(queue[1].is_current, false);
});

test('shows up to thirty previous items before the current queue', () => {
  const history = Array.from({length: 32}, (_, index) => ({queue_item_id: index, title: `Past ${index}`}));
  const queue = publicQueueItems([{queue_item_id: 40, title: 'Current'}], history);
  assert.equal(queue.length, 31);
  assert.equal(queue[0].queue_item_id, 2);
  assert.equal(queue[29].is_previous, true);
  assert.equal(queue[30].is_current, true);
});

test('retains a departed current item as bounded history', () => {
  let state = {items: [{queue_item_id: 1}, {queue_item_id: 2}], history: []};
  state = updateQueueState('Subscribed', {items: [{queue_item_id: 2}, {queue_item_id: 3}]}, state.items, state.history);
  assert.deepEqual(state.items.map(item => item.queue_item_id), [2, 3]);
  assert.deepEqual(state.history.map(item => item.queue_item_id), [1]);
  for (let id = 3; id < 45; id += 1) {
    state = updateQueueState('Subscribed', {items: [{queue_item_id: id}]}, state.items, state.history);
  }
  assert.equal(state.history.length, 30);
  assert.equal(state.history[0].queue_item_id, 14);
});

test('accepts incremental queue changes without disturbing order', () => {
  const initial = [{queue_item_id: 10}, {queue_item_id: 12}];
  const changed = queueItemsFromMessage('Changed', {
    items_added: [{index: 1, item: {queue_item_id: 11}}],
    items_changed: [{queue_item_id: 12, title: 'Updated'}]
  }, initial);
  assert.deepEqual(changed.map(item => item.queue_item_id), [10, 11, 12]);
  assert.equal(changed[2].title, 'Updated');
});

test('clears state on unsubscribe', () => {
  assert.deepEqual(queueItemsFromMessage('Unsubscribed', {}, [{queue_item_id: 1}]), []);
});
test('lead artists hide contributor lists without damaging real artist names', () => {
  assert.equal(leadArtist('Adele / Oren Waters / Carmen Carter'), 'Adele');
  assert.equal(leadArtist('AC/DC'), 'AC/DC');
  assert.equal(leadArtist('Earth, Wind & Fire'), 'Earth, Wind & Fire');
  assert.equal(leadArtist('Artist featuring Guest'), 'Artist');
  assert.equal(displayArtist({album_artist:'Adele',three_line:{line2:'Contributor / Guest'}}), 'Adele');
});
