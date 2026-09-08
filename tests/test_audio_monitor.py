import time
import unittest

import numpy as np

from audio_monitor import AudioLevels, AudioPreview


def wait_for(predicate):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Preview worker did not finish')


class AudioLevelsTests(unittest.TestCase):
    def test_stereo_channels_do_not_cancel_each_other(self):
        meter = AudioLevels()
        meter.feed('sys', np.column_stack((np.full(256, .5), np.full(256, -.5))))
        rows = meter.snapshot('sys')[1]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row[0] for row in rows], [.5, .5])
        self.assertEqual([row[1] for row in rows], [.5, .5])
        self.assertEqual(len(rows[0][2]), 48)
        self.assertIsNone(meter.snapshot('mic'))

    def test_silence_clipping_empty_and_buffer_reuse(self):
        meter = AudioLevels()
        data = np.array([[0.], [1.], [-1.], [0.]])
        meter.feed('mic', data, True)
        data[:] = 0
        self.assertEqual(meter.snapshot('mic')[1][0][0], 1)
        self.assertTrue(meter.snapshot('mic')[2])
        meter.feed('mic', data)
        self.assertEqual(meter.snapshot('mic')[1][0][0], 0)
        saved = meter.snapshot('mic')
        meter.feed('mic', np.empty((0, 1)))
        self.assertEqual(meter.snapshot('mic'), saved)

    def test_preview_configuration_and_release_after_partial_failure(self):
        class Stream:
            stopped = closed = False
            def start(self):
                pass
            def stop(self):
                self.stopped = True
            def close(self):
                self.closed = True
        class Driver:
            def __init__(self):
                self.stream = Stream()
                self.calls = []
            def query_devices(self, device):
                return {'max_input_channels': 2}
            def InputStream(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs['device'] == 7:
                    raise RuntimeError('device unavailable')
                kwargs['callback'](np.ones((64, 1)) * .2, 64, None, False)
                return self.stream
        driver = Driver()
        preview = AudioPreview(driver, 3, 7)
        try:
            wait_for(lambda: 'sys' in preview.errors)
            self.assertEqual(driver.calls[0]['device'], 3)
            self.assertEqual(driver.calls[0]['channels'], 1)
            self.assertEqual(driver.calls[1]['channels'], 2)
            self.assertEqual(driver.calls[0]['samplerate'], 44100)
            self.assertGreater(preview.levels.snapshot('mic')[1][0][0], .1)
            self.assertIn('unavailable', preview.errors['sys'])
        finally:
            preview.stop()
            wait_for(lambda: not preview.alive)
        self.assertTrue(driver.stream.stopped and driver.stream.closed)

    def test_none_devices_opens_no_stream(self):
        class Driver:
            def InputStream(self, **kwargs):
                raise AssertionError('No device was selected')
        preview = AudioPreview(Driver(), None, None)
        preview.stop()
        wait_for(lambda: not preview.alive)
        self.assertIsNone(preview.levels.snapshot('mic'))


if __name__ == '__main__':
    unittest.main()
