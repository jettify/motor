# Copyright 2014 MongoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Test Motor's asyncio test utilities."""

import asyncio
import contextlib
import io
import os
import unittest


from test.asyncio_tests import AsyncIOTestCase, asyncio_test


def run_test_case(case, suppress_output=True):
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(case)
    if suppress_output:
        stream = io.StringIO()
    else:
        stream = None

    runner = unittest.TextTestRunner(stream=stream)
    return runner.run(suite)


@contextlib.contextmanager
def set_environ(name, value):
    old_value = os.environ.get(name)
    os.environ[name] = value

    try:
        yield
    finally:
        if old_value is None:
            del os.environ[name]
        else:
            os.environ[name] = old_value


class TestAsyncIOTests(unittest.TestCase):
    def test_basic(self):
        class Test(AsyncIOTestCase):
            @asyncio_test
            def test(self):
                pass

        result = run_test_case(Test)
        self.assertEqual(1, result.testsRun)
        self.assertEqual(0, len(result.errors))

    def test_decorator_with_no_args(self):
        class TestPasses(AsyncIOTestCase):
            @asyncio_test()
            def test_decorated_with_no_args(self):
                pass

        result = run_test_case(TestPasses)
        self.assertEqual(0, len(result.errors))

        class TestFails(AsyncIOTestCase):
            @asyncio_test()
            def test_decorated_with_no_args(self):
                assert False

        result = run_test_case(TestFails)
        self.assertEqual(1, len(result.failures))

    def test_timeout_passed_as_positional(self):
        with self.assertRaises(TypeError):
            class _(AsyncIOTestCase):
                # Should be "timeout=10".
                @asyncio_test(10)
                def test_decorated_with_no_args(self):
                    pass

    def test_timeout(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.addCleanup(self.loop.close)
        self.addCleanup(setattr, self, 'loop', None)

        class Test(AsyncIOTestCase):
            @asyncio_test(timeout=0.01)
            def test_that_is_too_slow(self):
                yield from self.middle()

            @asyncio.coroutine
            def middle(self):
                yield from self.inner()

            @asyncio.coroutine
            def inner(self):
                yield from asyncio.sleep(1, loop=self.loop)

        with set_environ('ASYNC_TEST_TIMEOUT', '0'):
            result = run_test_case(Test)

        self.assertEqual(1, len(result.errors))
        case, text = result.errors[0]
        self.assertTrue('CancelledError' in text)
        self.assertTrue('timed out after 0.01 seconds' in text)

        # The traceback shows where the coroutine hung.
        self.assertTrue('test_that_is_too_slow' in text)
        self.assertTrue('middle' in text)
        self.assertTrue('inner' in text)

    def test_timeout_environment_variable(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.addCleanup(self.loop.close)
        self.addCleanup(setattr, self, 'loop', None)

        @asyncio_test
        def default_timeout(self):
            yield from asyncio.sleep(0.1, loop=self.loop)

        with set_environ('ASYNC_TEST_TIMEOUT', '0.2'):
            # No error, sleeps for 0.1 seconds and the timeout is 0.2 seconds.
            default_timeout(self)

        @asyncio_test(timeout=0.1)
        def custom_timeout(self):
            yield from asyncio.sleep(0.2, loop=self.loop)

        with set_environ('ASYNC_TEST_TIMEOUT', '0'):
            # No error, default timeout of 5 seconds overrides '0'.
            default_timeout(self)

        with set_environ('ASYNC_TEST_TIMEOUT', '0'):
            with self.assertRaises(asyncio.CancelledError):
                custom_timeout(self)

        with set_environ('ASYNC_TEST_TIMEOUT', '1'):
            # No error, 1-second timeout from environment overrides custom
            # timeout of 0.1 seconds.
            custom_timeout(self)

    def test_failure(self):
        class Test(AsyncIOTestCase):
            @asyncio_test
            def test_that_fails(self):
                yield from self.middle()

            @asyncio.coroutine
            def middle(self):
                yield from self.inner()

            @asyncio.coroutine
            def inner(self):
                assert False, 'expected error'

        result = run_test_case(Test)
        self.assertEqual(1, len(result.failures))
        case, text = result.failures[0]
        self.assertFalse('CancelledError' in text)
        self.assertTrue('AssertionError' in text)
        self.assertTrue('expected error' in text)

        # The traceback shows where the coroutine raised.
        self.assertTrue('test_that_fails' in text)
        self.assertTrue('middle' in text)
        self.assertTrue('inner' in text)

    def test_undecorated(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.addCleanup(self.loop.close)
        self.addCleanup(setattr, self, 'loop', None)

        class Test(AsyncIOTestCase):
            def test_that_should_be_decorated(self):
                yield from asyncio.sleep(0.01, loop=self.loop)

        result = run_test_case(Test)
        self.assertEqual(1, len(result.errors))
        case, text = result.errors[0]
        self.assertFalse('CancelledError' in text)
        self.assertTrue('TypeError' in text)
        self.assertTrue('should be decorated with @asyncio_test' in text)

    def test_other_return(self):
        class Test(AsyncIOTestCase):
            def test_other_return(self):
                return 42

        result = run_test_case(Test)
        self.assertEqual(len(result.errors), 1)
        case, text = result.errors[0]
        self.assertIn('Return value from test method ignored', text)


if __name__ == '__main__':
    unittest.main()
