'use strict';
const {displayArtist} = require('./artist-name');
const QUEUE_HISTORY_LIMIT = 30;

function queueItemsFromMessage(command, message, previous = []) {
  const data = message || {};
  if (command === 'Unsubscribed') return [];
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(data.queue_items)) return data.queue_items;
  if (command !== 'Changed') return previous;

  let items = [...previous];
  for (const removed of data.items_removed || []) {
    const id = typeof removed === 'object' ? removed.queue_item_id : removed;
    items = items.filter(item => item.queue_item_id !== id);
  }
  for (const changed of data.items_changed || []) {
    const index = items.findIndex(item => item.queue_item_id === changed.queue_item_id);
    if (index >= 0) items[index] = {...items[index], ...changed};
  }
  for (const added of data.items_added || []) {
    const item = added.item || added;
    const index = Number.isInteger(added.index) ? added.index : items.length;
    items.splice(Math.max(0, Math.min(index, items.length)), 0, item);
  }
  for (const change of data.changes || []) {
    const operation = change.operation || change.op;
    const index = Math.max(0, Number(change.index) || 0);
    if (operation === 'remove') items.splice(index, Number(change.count) || 1);
    if (operation === 'insert') items.splice(index, 0, ...(change.items || (change.item ? [change.item] : [])));
    if (operation === 'replace') items.splice(index, Number(change.count) || 1, ...(change.items || (change.item ? [change.item] : [])));
  }
  return items;
}

function publicQueueItems(items, history = []) {
  const previous = (history || []).slice(-QUEUE_HISTORY_LIMIT).map(item => ({...publicQueueItem(item), is_current: false, is_previous: true}));
  return previous.concat((items || []).map((item, index) => ({
    ...publicQueueItem(item), is_current: index === 0, is_previous: false
  }))).filter(item => item.queue_item_id !== undefined && item.queue_item_id !== null);
}

function publicQueueItem(item) {
  const lines = item.three_line || item.two_line || item.one_line || {};
  return {
    queue_item_id: item.queue_item_id,
    title: lines.line1 || item.title || 'Untitled track',
    artist: displayArtist(item),
    album: lines.line3 || item.album || '',
    length: Number(item.length) || null,
    image_key: item.image_key || null
  };
}

function updateQueueState(command, message, items = [], history = [], limit = 100) {
  const previousCurrent = items[0];
  const nextItems = queueItemsFromMessage(command, message, items).slice(0, limit);
  let nextHistory = [...history];
  if (previousCurrent && (!nextItems[0] || previousCurrent.queue_item_id !== nextItems[0].queue_item_id) &&
      !nextItems.some(item => item.queue_item_id === previousCurrent.queue_item_id)) {
    nextHistory = nextHistory.filter(item => item.queue_item_id !== previousCurrent.queue_item_id);
    nextHistory.push(previousCurrent);
    nextHistory = nextHistory.slice(-QUEUE_HISTORY_LIMIT);
  }
  return {items: nextItems, history: nextHistory};
}

module.exports = {queueItemsFromMessage, publicQueueItems, updateQueueState};
