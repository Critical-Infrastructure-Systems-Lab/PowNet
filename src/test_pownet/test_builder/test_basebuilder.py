"""test_basebuilder.py: Unit tests for the ComponentBuilder abstract base class."""

import unittest
from unittest.mock import MagicMock, patch

# Import ComponentBuilder from its actual location
from pownet.builder.basebuilder import ComponentBuilder

# PATCH_BASE should be the module where ComponentBuilder is defined,
# as this is the context where its internal imports (like gp and SystemInput) are resolved.
PATCH_BASE = "pownet.builder.basebuilder"

# We need ABC for creating test subclasses
from abc import ABC, abstractmethod  # ABC is implicitly used by ComponentBuilder


# Minimal concrete implementation for testing ComponentBuilder
class MinimalConcreteBuilder(ComponentBuilder):
    """A minimal concrete subclass for testing ComponentBuilder."""

    def add_variables(self, step_k: int) -> None:
        """Mock implementation."""
        pass

    def get_fixed_objective_terms(self) -> MagicMock:  # Actual type is gp.LinExpr
        """Mock implementation."""
        return MagicMock(name="MockLinExpr_fixed")

    def get_variable_objective_terms(
        self, step_k: int, **kwargs
    ) -> MagicMock:  # Actual type is gp.LinExpr
        """Mock implementation."""
        return MagicMock(name="MockLinExpr_variable")

    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Mock implementation."""
        pass

    def update_variables(self, step_k: int) -> None:
        """Mock implementation."""
        pass

    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        """Mock implementation."""
        pass

    def get_variables(
        self,
    ) -> dict[str, MagicMock]:  # Actual type is dict[str, gp.tupledict]
        """Mock implementation."""
        return {"mock_var": MagicMock(name="MockTupleDict")}


# An incomplete subclass for testing abstract method enforcement
class IncompleteBuilder(ComponentBuilder):
    """An incomplete subclass that misses some abstract methods."""

    def add_variables(self, step_k: int) -> None:
        pass

    def get_fixed_objective_terms(self) -> MagicMock:
        return MagicMock(name="MockLinExpr_fixed_incomplete")

    # Missing: get_variable_objective_terms, add_constraints, etc.
    def get_variables(self) -> dict[str, MagicMock]:
        return {"mock_var_incomplete": MagicMock(name="MockTupleDict_incomplete")}

    # To make it instantiable for other tests, we would need to implement all other abstract methods.
    # For this test, we want it to remain abstract.
    @abstractmethod  # Explicitly mark remaining methods as abstract if not implemented
    def get_variable_objective_terms(self, step_k: int, **kwargs) -> MagicMock:
        pass

    @abstractmethod
    def add_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        pass

    @abstractmethod
    def update_variables(self, step_k: int) -> None:
        pass

    @abstractmethod
    def update_constraints(self, step_k: int, init_conds: dict, **kwargs) -> None:
        pass


@patch(f"{PATCH_BASE}.SystemInput", autospec=True)
@patch(f"{PATCH_BASE}.gp")  # Patch the 'gp' alias used in basebuilder.py
class TestComponentBuilder(unittest.TestCase):

    def _configure_mock_gp_alias(self, mock_gp_alias):
        """Helper to configure the mocked 'gp' alias and its attributes."""
        mock_gp_alias.Model = MagicMock(name="MockGPModelClass")
        mock_gp_alias.LinExpr = MagicMock(name="MockGPLinExprClass")
        mock_gp_alias.tupledict = MagicMock(name="MockGPTupleDictClass")
        return mock_gp_alias.Model.return_value  # Return a mock model instance

    def test_component_builder_is_abc_and_cannot_be_instantiated(
        self, mock_gp_alias: MagicMock, mock_system_input_class: MagicMock
    ):
        """Test that ComponentBuilder cannot be instantiated directly."""
        mock_model_instance = self._configure_mock_gp_alias(mock_gp_alias)
        # Ensure all required arguments for SystemInput are provided
        mock_inputs_instance = mock_system_input_class(
            input_folder="dummy",
            model_name="test_model",  # Assuming model_name is a required arg for SystemInput
            year=2023,  # Assuming year is a required arg
            sim_horizon=24,  # Assuming sim_horizon is a required arg for constructor
        )
        # ComponentBuilder uses inputs.sim_horizon, so ensure it's set on the mock if not by constructor
        mock_inputs_instance.sim_horizon = 10  # This is what ComponentBuilder will use

        with self.assertRaisesRegex(
            TypeError,
            # Simplified regex to match the beginning of the actual error message
            r"Can't instantiate abstract class ComponentBuilder",
        ):
            ComponentBuilder(mock_model_instance, mock_inputs_instance)

    def test_concrete_subclass_instantiation_and_init_attributes(
        self, mock_gp_alias: MagicMock, mock_system_input_class: MagicMock
    ):
        """Test instantiation of a concrete subclass and __init__ attributes."""
        mock_model_instance = self._configure_mock_gp_alias(mock_gp_alias)

        mock_inputs_instance = mock_system_input_class(
            input_folder="dummy_concrete_path",
            model_name="test_model_concrete",
            year=2023,
            sim_horizon=24,  # Initial value for SystemInput constructor
        )
        # ComponentBuilder's __init__ uses inputs.sim_horizon.
        # We are testing that ComponentBuilder correctly picks up this value.
        # So, the value set here is what we expect ComponentBuilder to use.
        mock_inputs_instance.sim_horizon = 5

        builder = MinimalConcreteBuilder(
            model=mock_model_instance, inputs=mock_inputs_instance
        )

        self.assertIsInstance(builder, MinimalConcreteBuilder)
        self.assertIsInstance(builder, ComponentBuilder)
        self.assertEqual(builder.model, mock_model_instance)
        self.assertEqual(builder.inputs, mock_inputs_instance)
        # Test against the value that ComponentBuilder's __init__ should have used
        self.assertEqual(builder.sim_horizon, 5)
        self.assertEqual(list(builder.timesteps), list(range(1, 5 + 1)))

    def test_incomplete_subclass_cannot_be_instantiated(
        self, mock_gp_alias: MagicMock, mock_system_input_class: MagicMock
    ):
        """Test that a subclass missing abstract methods cannot be instantiated."""
        mock_model_instance = self._configure_mock_gp_alias(mock_gp_alias)
        mock_inputs_instance = mock_system_input_class(
            input_folder="dummy_incomplete_path",
            model_name="test_model_incomplete",
            year=2023,
            sim_horizon=24,
        )
        mock_inputs_instance.sim_horizon = 3

        with self.assertRaisesRegex(
            TypeError,
            # Simplified regex to match the beginning of the actual error message
            r"Can't instantiate abstract class IncompleteBuilder",
        ):
            IncompleteBuilder(mock_model_instance, mock_inputs_instance)

    def test_abstract_methods_exist(
        self, mock_gp_alias: MagicMock, mock_system_input_class: MagicMock
    ):
        """Check that all declared abstract methods are indeed marked as abstract."""
        expected_abstract_methods = frozenset(
            {  # Use frozenset for direct comparison
                "add_variables",
                "get_fixed_objective_terms",
                "get_variable_objective_terms",
                "add_constraints",
                "update_variables",
                "update_constraints",
                "get_variables",
            }
        )
        self.assertEqual(
            ComponentBuilder.__abstractmethods__, expected_abstract_methods
        )


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
