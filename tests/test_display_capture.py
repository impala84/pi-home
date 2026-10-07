import base64
import threading
import unittest
from unittest.mock import patch

from pi_bus_time_display.config import Config
from pi_bus_time_display.server import State


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=')


class DisplayCaptureTests(unittest.TestCase):
    def test_preview_navigation_is_delivered_to_native_display(self):
        state = State(Config())
        request = state.request_display_view('browse', 'open', 'album-key')
        self.assertEqual(request['browse_action'], 'open')
        self.assertEqual(request['item_key'], 'album-key')
        self.assertEqual(state.controls_snapshot()['display_view_request'], request)

    def test_display_view_request_has_a_fresh_identity(self):
        state = State(Config())
        first = state.request_display_view('daily')
        self.assertEqual(state.controls_snapshot()['display_view_request'], first)
        second = state.request_display_view('releases')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['view'], 'releases')

    def test_capture_round_trip_is_ephemeral(self):
        state = State(Config())
        def respond(_timeout):
            request_id = state.controls_snapshot()['capture_request']
            state.complete_display_capture({'id': request_id, 'image': base64.b64encode(PNG).decode()})
            return True
        with patch.object(threading.Event, 'wait', side_effect=respond):
            self.assertEqual(state.capture_display(), PNG)
        self.assertIsNone(state.controls_snapshot()['capture_request'])

    def test_capture_failure_is_reported_and_cleared(self):
        state = State(Config())
        def respond(_timeout):
            state.complete_display_capture({'id': state.controls_snapshot()['capture_request'], 'error': 'Display is asleep'})
            return True
        with patch.object(threading.Event, 'wait', side_effect=respond):
            with self.assertRaisesRegex(RuntimeError, 'Display is asleep'):
                state.capture_display()
        self.assertIsNone(state.display_capture)

    def test_capture_timeout_clears_pending_request(self):
        state = State(Config())
        with self.assertRaisesRegex(RuntimeError, 'did not respond'):
            state.capture_display(timeout=0)
        self.assertIsNone(state.display_capture)

    def test_unrequested_capture_is_rejected(self):
        with self.assertRaises(ValueError):
            State(Config()).complete_display_capture({'id': 'fake', 'image': base64.b64encode(PNG).decode()})

    def test_wrong_ticket_invalid_image_and_duplicate_reply_are_rejected(self):
        state = State(Config())
        def respond(_timeout):
            request_id = state.controls_snapshot()['capture_request']
            for data in ({'id':'wrong','image':base64.b64encode(PNG).decode()}, {'id':request_id,'image':'invalid'}, {'id':request_id,'image':base64.b64encode(b'not a PNG').decode()}):
                with self.assertRaises(ValueError):
                    state.complete_display_capture(data)
            data = {'id':request_id,'image':base64.b64encode(PNG).decode()}
            state.complete_display_capture(data)
            with self.assertRaises(ValueError):
                state.complete_display_capture(data)
            return True
        with patch.object(threading.Event, 'wait', side_effect=respond):
            self.assertEqual(state.capture_display(), PNG)

    def test_concurrent_capture_does_not_replace_first_request(self):
        state = State(Config())
        def respond(_timeout):
            request_id = state.controls_snapshot()['capture_request']
            with self.assertRaisesRegex(RuntimeError, 'already in progress'):
                state.capture_display(timeout=0)
            self.assertEqual(state.controls_snapshot()['capture_request'], request_id)
            state.complete_display_capture({'id':request_id,'image':base64.b64encode(PNG).decode()})
            return True
        with patch.object(threading.Event, 'wait', side_effect=respond):
            self.assertEqual(state.capture_display(), PNG)
