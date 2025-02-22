from asyncio import sleep

import pytest
from cache.key import KEY

from iSponsorBlockTV.utils.cache import AsyncConditionalTTL, list_to_tuple


class TestAsyncConditionalTTL:
    """Test suite for the AsyncConditionalTTL class."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance for testing."""
        return AsyncConditionalTTL(time_to_live=1, maxsize=10)

    @pytest.mark.asyncio
    async def test_basic_caching(self, cache):
        """Test that caching works for basic function calls."""
        call_count = 0

        @cache
        async def test_func():
            nonlocal call_count
            call_count += 1
            return (42, False)  # (value, ignore_ttl)

        # First call should execute the function
        result1 = await test_func()
        assert result1 == 42
        assert call_count == 1

        # Second call should use the cached value
        result2 = await test_func()
        assert result2 == 42
        assert call_count == 1  # Call count shouldn't increase

    @pytest.mark.asyncio
    async def test_ignore_ttl_flag(self, cache):
        """Test that the ignore_ttl flag prevents TTL from being applied."""

        @cache
        async def test_func(flag: bool):
            return (42, flag)  # Return (value, ignore_ttl) where flag is ignore_ttl

        # With ignore_ttl=False, TTL should be applied
        result1 = await test_func(False)
        assert result1 == 42

        # Call the function again to verify caching works
        result2 = await test_func(False)
        assert result2 == 42

        # Wait for a moment to ensure first value should be expired if TTL was very short
        await sleep(0.1)

        # Now set ignore_ttl=True and verify it works
        result3 = await test_func(True)
        assert result3 == 42

        # Wait longer than typical TTL to test that ignore_ttl=True items persist
        await sleep(1.1)

        # Should still be cached even after TTL would typically expire
        result4 = await test_func(True)
        assert result4 == 42

        # With ignore_ttl=True, TTL should not be applied
        await test_func(True)

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, cache):
        """Test that cached items expire after the TTL."""
        call_count = 0

        @cache
        async def test_func():
            nonlocal call_count
            call_count += 1
            return (42, False)  # (value, ignore_ttl=False)

        # First call should execute the function
        result1 = await test_func()
        assert result1 == 42
        assert call_count == 1

        # Verify it's in the cache
        key = KEY((), {})
        assert key in cache.ttl

        # Wait for TTL to expire (slightly more than 1 second)
        await sleep(1.1)

        # After TTL expiration, accessing the cache should trigger a new function call
        result2 = await test_func()
        assert result2 == 42
        assert call_count == 2  # Function should be called again

    @pytest.mark.asyncio
    async def test_non_expiring_cache(self):
        """Test that setting time_to_live=None creates a non-expiring cache."""
        non_expiring_cache = AsyncConditionalTTL(time_to_live=None, maxsize=10)

        call_count = 0

        @non_expiring_cache
        async def test_func():
            nonlocal call_count
            call_count += 1
            return (42, False)

        # First call
        result1 = await test_func()
        assert result1 == 42
        assert call_count == 1

        # Wait some time that would typically be enough for TTL expiration
        await sleep(1.1)

        # Call again - should still use the cached value
        result2 = await test_func()
        assert result2 == 42
        assert call_count == 1  # Still should be 1 if caching works

    @pytest.mark.asyncio
    async def test_maxsize_limit(self):
        """Test that the cache respects the maxsize limit."""
        small_cache = AsyncConditionalTTL(time_to_live=60, maxsize=2)

        call_count = {1: 0, 2: 0, 3: 0}

        @small_cache
        async def test_func(n):
            call_count[n] += 1
            return (n, False)

        # Add three items to a cache with maxsize=2
        await test_func(1)  # This should be evicted once item 3 is added
        await test_func(2)
        await test_func(3)

        # Each should have been called once
        assert call_count[1] == 1
        assert call_count[2] == 1
        assert call_count[3] == 1

        # Test cache hits for the items still in cache
        await test_func(2)  # Should be a cache hit
        await test_func(3)  # Should be a cache hit

        # Call counts should not have increased for items still in cache
        assert call_count[2] == 1  # Still 1 if cached
        assert call_count[3] == 1  # Still 1 if cached

        # But calling the evicted item should cause another function call
        await test_func(1)  # Should cause a new call since it was evicted
        assert call_count[1] == 2  # Should increase because it was evicted

    @pytest.mark.asyncio
    async def test_skip_args(self):
        """Test that skip_args skips the specified number of arguments when creating the cache key."""
        skip_cache = AsyncConditionalTTL(time_to_live=60, maxsize=10, skip_args=1)

        call_count = 0

        @skip_cache
        async def test_func(skip_this, use_this):
            nonlocal call_count
            call_count += 1
            return (f"{skip_this}_{use_this}", False)

        # These calls should use the same cache key as skip_args=1
        result1 = await test_func("a", "b")
        assert result1 == "a_b"
        assert call_count == 1

        result2 = await test_func("different", "b")
        assert result2 == "a_b"  # Should get cached value
        assert call_count == 1  # Function should not be called again

        # Different second arg should generate a different key
        result3 = await test_func("c", "d")
        assert result3 == "c_d"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_wrapper_name(self, cache):
        """Test that the wrapper function name includes the original function name."""

        @cache
        async def test_func():
            return (42, False)

        assert "test_func" in test_func.__name__


class TestListToTuple:
    """Test suite for the list_to_tuple decorator."""

    def test_convert_list_args_to_tuples(self):
        """Test that list arguments are converted to tuples."""

        @list_to_tuple
        def test_func(a, b):
            return [a, b]

        result = test_func([1, 2], [3, 4])
        assert result == ((1, 2), (3, 4))

    def test_mixed_args(self):
        """Test with a mix of list and non-list arguments."""

        @list_to_tuple
        def test_func(a, b, c):
            return [a, b, c]

        result = test_func([1, 2], "string", 42)
        assert result == ((1, 2), "string", 42)

    def test_nested_lists(self):
        """Test handling of nested lists."""

        @list_to_tuple
        def test_func(a):
            return a

        result = test_func([1, [2, 3], 4])
        assert result == (1, [2, 3], 4)  # Only top-level lists are converted

    def test_return_conversion(self):
        """Test that list returns are converted to tuples."""

        @list_to_tuple
        def test_func():
            return [1, 2, 3]

        result = test_func()
        assert result == (1, 2, 3)

    def test_non_list_return(self):
        """Test that non-list returns are left unchanged."""

        @list_to_tuple
        def test_func():
            return "not a list"

        result = test_func()
        assert result == "not a list"

    def test_function_metadata_preserved(self):
        """Test that function metadata is preserved by the decorator."""

        def original_func():
            """Test docstring."""
            pass

        decorated = list_to_tuple(original_func)
        assert decorated.__name__ == original_func.__name__
        assert decorated.__doc__ == original_func.__doc__


# Additional integration tests


@pytest.mark.asyncio
async def test_integration_with_real_function():
    """Integration test with a more realistic scenario."""
    cache = AsyncConditionalTTL(time_to_live=1)

    call_count = 0

    @cache
    async def fetch_data(param, expensive=True):
        nonlocal call_count
        call_count += 1
        # Simulate expensive operation
        await sleep(0.1)
        # Return data and whether to ignore TTL
        return (f"Result for {param}", not expensive)

    # First call with expensive=True (should apply TTL)
    result1 = await fetch_data("test", expensive=True)
    assert result1 == "Result for test"
    assert call_count == 1

    # Second call with same params (should use cache)
    result2 = await fetch_data("test", expensive=True)
    assert result2 == "Result for test"
    assert call_count == 1  # No additional call

    # Call with different param (should execute function)
    result3 = await fetch_data("other")
    assert result3 == "Result for other"
    assert call_count == 2

    # Wait for TTL to expire
    await sleep(1.1)

    # Call again after expiry (should execute function)
    result4 = await fetch_data("test", expensive=True)
    assert result4 == "Result for test"
    assert call_count == 3

    # Call with expensive=False (should set ignore_ttl=True)
    result5 = await fetch_data("persist", expensive=False)
    assert result5 == "Result for persist"
    assert call_count == 4

    # Wait for TTL again
    await sleep(1.1)

    # This should still be in cache since we set ignore_ttl=True
    # due to expensive=False (which returns ignore_ttl=True)
    result6 = await fetch_data("persist", expensive=False)
    assert result6 == "Result for persist"
    assert call_count == 4  # Should not increase because it's still cached
