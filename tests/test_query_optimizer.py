"""
Tests for query optimizer module.

Tests optimization strategies:
- Filter pushdown before joins
- Filter combination
- Cost estimation
- Execution plan generation
"""

import pytest
from nba_mcp.data.query_optimizer import (
    QueryOptimizer,
    CostEstimator,
    QueryOperation,
    OperationType,
    ExecutionPlan,
    get_query_optimizer,
    reset_query_optimizer,
)


class TestCostEstimator:
    """Test cost estimation for different operations."""

    def setup_method(self):
        """Reset before each test."""
        self.estimator = CostEstimator()

    def test_fetch_cost_estimation(self):
        """Test cost estimation for fetch operations."""
        cost, rows = self.estimator.estimate_fetch_cost(
            "team_game_log",
            {"team": "Lakers", "season": "2023-24"}
        )

        # Should have base cost + data cost
        assert cost > 1000.0  # Base cost
        assert rows == 82  # Estimated rows for team_game_log

    def test_filter_cost_estimation(self):
        """Test cost estimation for filter operations."""
        cost, rows = self.estimator.estimate_filter_cost(
            rows=100,
            num_filters=2
        )

        # Filter cost should be very low (DuckDB is fast)
        assert cost > 0
        assert cost < 100  # Should be much less than fetch cost

        # Each filter reduces rows by ~50%
        assert rows == 25  # 100 * 0.5^2

    def test_join_cost_estimation(self):
        """Test cost estimation for join operations."""
        cost, rows = self.estimator.estimate_join_cost(
            left_rows=100,
            right_rows=50,
            join_type="inner"
        )

        assert cost > 0
        assert rows > 0
        assert rows <= min(100, 50)  # Inner join reduces rows

    def test_join_types(self):
        """Test join cost estimation for different join types."""
        left_rows, right_rows = 100, 50

        # Inner join
        _, inner_rows = self.estimator.estimate_join_cost(left_rows, right_rows, "inner")

        # Left join
        _, left_join_rows = self.estimator.estimate_join_cost(left_rows, right_rows, "left")
        assert left_join_rows == left_rows  # Left join preserves left rows

        # Right join
        _, right_join_rows = self.estimator.estimate_join_cost(left_rows, right_rows, "right")
        assert right_join_rows == right_rows  # Right join preserves right rows

        # Outer join
        _, outer_rows = self.estimator.estimate_join_cost(left_rows, right_rows, "outer")
        assert outer_rows == max(left_rows, right_rows)

    def test_aggregate_cost_estimation(self):
        """Test cost estimation for aggregate operations."""
        cost, rows = self.estimator.estimate_aggregate_cost(
            rows=1000,
            num_groups=10
        )

        assert cost > 0
        assert rows == 10  # Output rows = number of groups

    def test_sort_cost_estimation(self):
        """Test cost estimation for sort operations."""
        cost, rows = self.estimator.estimate_sort_cost(rows=1000)

        assert cost > 0
        assert rows == 1000  # Sort doesn't change row count


class TestQueryOptimizer:
    """Test query optimization strategies."""

    def setup_method(self):
        """Reset before each test."""
        reset_query_optimizer()
        self.optimizer = QueryOptimizer()

    def test_filter_pushdown_before_join(self):
        """Test that filters are pushed before joins."""
        operations = [
            {"op": "fetch", "endpoint": "team_game_log", "params": {}},
            {"op": "join", "right": {}, "on": "TEAM_ID"},
            {"op": "filter", "filters": {"WL": ["==", "W"]}},
        ]

        plan = self.optimizer.optimize(operations)

        # Find positions of filter and join
        filter_pos = None
        join_pos = None

        for i, op in enumerate(plan.operations):
            if op.op_type == OperationType.FILTER:
                filter_pos = i
            if op.op_type == OperationType.JOIN:
                join_pos = i

        # Filter should come before join
        assert filter_pos is not None
        assert join_pos is not None
        assert filter_pos < join_pos

        # Check optimization was applied
        assert "filter_pushdown_before_joins" in plan.optimization_applied

    def test_filter_combination(self):
        """Test that consecutive filters are combined."""
        operations = [
            {"op": "fetch", "endpoint": "team_standings", "params": {}},
            {"op": "filter", "filters": {"conference": ["==", "West"]}},
            {"op": "filter", "filters": {"wins": [">=", 40]}},
        ]

        plan = self.optimizer.optimize(operations)

        # Count filter operations
        filter_count = sum(1 for op in plan.operations if op.op_type == OperationType.FILTER)

        # Should have only 1 combined filter instead of 2
        assert filter_count == 1

        # Check optimization was applied
        assert "filter_combination" in plan.optimization_applied

        # Check combined filter has both conditions
        filter_op = next(op for op in plan.operations if op.op_type == OperationType.FILTER)
        filters = filter_op.params.get("filters", {})
        assert "conference" in filters
        assert "wins" in filters

    def test_multiple_optimizations(self):
        """Test multiple optimizations applied together."""
        operations = [
            {"op": "fetch", "endpoint": "team_game_log", "params": {}},
            {"op": "filter", "filters": {"WL": ["==", "W"]}},
            {"op": "join", "right": {}, "on": "TEAM_ID"},
            {"op": "filter", "filters": {"PTS": [">=", 110]}},
        ]

        plan = self.optimizer.optimize(operations)

        # Should have applied filter combination AND pushdown
        assert "filter_combination" in plan.optimization_applied
        assert "filter_pushdown_before_joins" in plan.optimization_applied

    def test_cost_estimation_updated(self):
        """Test that costs are estimated for all operations."""
        operations = [
            {"op": "fetch", "endpoint": "team_game_log", "params": {"team": "Lakers"}},
            {"op": "filter", "filters": {"WL": ["==", "W"]}},
        ]

        plan = self.optimizer.optimize(operations)

        # All operations should have estimated costs
        for op in plan.operations:
            assert op.estimated_cost > 0
            assert op.estimated_rows >= 0

        # Total cost should be sum of operation costs
        assert plan.total_estimated_cost > 0

    def test_no_optimization_needed(self):
        """Test that already-optimal plans are not changed."""
        operations = [
            {"op": "fetch", "endpoint": "team_standings", "params": {}},
            {"op": "filter", "filters": {"conference": ["==", "West"]}},
        ]

        plan = self.optimizer.optimize(operations)

        # No optimizations should be needed
        assert len(plan.optimization_applied) == 0

        # Operations should remain in same order
        assert plan.operations[0].op_type == OperationType.FETCH
        assert plan.operations[1].op_type == OperationType.FILTER


class TestQueryOperation:
    """Test QueryOperation class."""

    def test_operation_creation(self):
        """Test creating a QueryOperation."""
        op = QueryOperation(
            op_type=OperationType.FETCH,
            params={"endpoint": "team_standings"}
        )

        assert op.op_type == OperationType.FETCH
        assert op.params["endpoint"] == "team_standings"
        assert op.op_id is not None  # Auto-generated

    def test_operation_with_id(self):
        """Test creating operation with custom ID."""
        op = QueryOperation(
            op_type=OperationType.FILTER,
            params={"filters": {}},
            op_id="custom_id_123"
        )

        assert op.op_id == "custom_id_123"


class TestExecutionPlan:
    """Test ExecutionPlan class."""

    def test_plan_creation(self):
        """Test creating an ExecutionPlan."""
        ops = [
            QueryOperation(
                op_type=OperationType.FETCH,
                params={},
                estimated_cost=1000.0
            ),
            QueryOperation(
                op_type=OperationType.FILTER,
                params={},
                estimated_cost=10.0
            ),
        ]

        plan = ExecutionPlan(operations=ops)

        assert len(plan.operations) == 2
        assert plan.total_estimated_cost == 1010.0

    def test_plan_with_optimizations(self):
        """Test plan with recorded optimizations."""
        ops = [QueryOperation(op_type=OperationType.FETCH, params={})]

        plan = ExecutionPlan(
            operations=ops,
            optimization_applied=["filter_pushdown", "filter_combination"]
        )

        assert len(plan.optimization_applied) == 2
        assert "filter_pushdown" in plan.optimization_applied


class TestOptimizationScenarios:
    """Test real-world optimization scenarios."""

    def setup_method(self):
        """Reset before each test."""
        self.optimizer = QueryOptimizer()

    def test_complex_query_optimization(self):
        """Test optimization of complex multi-step query."""
        operations = [
            {"op": "fetch", "endpoint": "team_game_log", "params": {"team": "Lakers"}},
            {"op": "join", "right": {}, "on": "TEAM_ID"},
            {"op": "filter", "filters": {"WL": ["==", "W"]}},
            {"op": "filter", "filters": {"PTS": [">=", 110]}},
            {"op": "join", "right": {}, "on": "GAME_ID"},
            {"op": "filter", "filters": {"HOME": ["==", True]}},
        ]

        plan = self.optimizer.optimize(operations)

        # Check multiple optimizations were applied
        assert len(plan.optimization_applied) >= 2

        # Total cost should be calculated
        assert plan.total_estimated_cost > 0

    def test_filter_only_optimization(self):
        """Test optimization with only filters."""
        operations = [
            {"op": "fetch", "endpoint": "team_standings", "params": {}},
            {"op": "filter", "filters": {"conference": ["==", "West"]}},
            {"op": "filter", "filters": {"wins": [">=", 40]}},
            {"op": "filter", "filters": {"losses": ["<=", 42]}},
        ]

        plan = self.optimizer.optimize(operations)

        # Should combine all filters into one
        filter_count = sum(1 for op in plan.operations if op.op_type == OperationType.FILTER)
        assert filter_count == 1

        # Should have applied filter combination
        assert "filter_combination" in plan.optimization_applied


class TestGlobalOptimizer:
    """Test global optimizer singleton."""

    def test_get_optimizer_singleton(self):
        """Test that get_query_optimizer returns singleton."""
        reset_query_optimizer()

        opt1 = get_query_optimizer()
        opt2 = get_query_optimizer()

        assert opt1 is opt2  # Same instance

    def test_reset_optimizer(self):
        """Test resetting global optimizer."""
        opt1 = get_query_optimizer()
        reset_query_optimizer()
        opt2 = get_query_optimizer()

        assert opt1 is not opt2  # Different instances after reset
