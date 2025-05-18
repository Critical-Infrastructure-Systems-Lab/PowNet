"""test_builder.py: Unit tests for the ModelBuilder class."""

import unittest
from unittest.mock import MagicMock, patch, call

from pownet import ModelBuilder

from gurobipy import GRB  # Used directly for GRB.MINIMIZE


# Custom Mock for gurobipy.LinExpr to make objective summation testable
class MockLinExpr:
    def __init__(self, value=0.0, name=""):
        self.value = float(value)
        self._name = name  # For debugging

    def __add__(self, other):
        other_value = other.value if isinstance(other, MockLinExpr) else float(other)
        return MockLinExpr(self.value + other_value, f"{self._name}_add")

    def __radd__(self, other):  # For sum() or when LinExpr is on the right
        other_value = other.value if isinstance(other, MockLinExpr) else float(other)
        return MockLinExpr(self.value + other_value, f"{self._name}_radd")

    def __iadd__(self, other):
        other_value = other.value if isinstance(other, MockLinExpr) else float(other)
        self.value += other_value
        return self

    def copy(self):
        return MockLinExpr(self.value, f"{self._name}_copy")

    def getValue(self):
        return self.value

    def __repr__(self):
        return f"MockLinExpr({self.value}, name='{self._name}')"


PATCH_BASE = "pownet.core.model_builder"


# The order of decorators matters: they are applied from bottom to top.
# The mock for the bottom-most decorator is the first argument to the test method.
@patch(f"{PATCH_BASE}.SystemBuilder", autospec=True)
@patch(f"{PATCH_BASE}.EnergyStorageUnitBuilder", autospec=True)
@patch(f"{PATCH_BASE}.NonDispatchUnitBuilder", autospec=True)
@patch(f"{PATCH_BASE}.HydroUnitBuilder", autospec=True)
@patch(f"{PATCH_BASE}.ThermalUnitBuilder", autospec=True)
@patch(
    f"{PATCH_BASE}.PowerSystemModel", autospec=True
)  # This is from pownet.optim_model but imported into PATCH_BASE
@patch(
    f"{PATCH_BASE}.gp.LinExpr",
    side_effect=lambda name_suffix="": MockLinExpr(
        0.0, f"initial_LinExpr_{name_suffix}"
    ),
)
@patch(f"{PATCH_BASE}.gp.Model", autospec=True)  # gp is an alias in PATCH_BASE
@patch(
    f"{PATCH_BASE}.SystemInput", autospec=True
)  # SystemInput is from ..input but imported into PATCH_BASE
class TestModelBuilder(unittest.TestCase):

    # setUp is not strictly needed here as mocks are passed directly via decorators.
    # def setUp(self):
    #     pass

    def _configure_mock_builder(
        self, mock_builder_instance, name="test", fixed_obj_val=1.0, var_obj_val=10.0
    ):
        """Helper to configure a mock sub-builder."""
        mock_builder_instance.get_fixed_objective_terms.return_value = MockLinExpr(
            fixed_obj_val, f"{name}_fixed_obj"
        )
        mock_builder_instance.get_variable_objective_terms.return_value = MockLinExpr(
            var_obj_val, f"{name}_var_obj"
        )

        # Mock attributes that SystemBuilder.add_constraints might need
        mock_builder_instance.spin = MagicMock(name=f"{name}_spin_var")
        mock_builder_instance.vpowerbar = MagicMock(name=f"{name}_vpowerbar_var")
        mock_builder_instance.status = MagicMock(name=f"{name}_status_var")
        mock_builder_instance.pthermal = MagicMock(name=f"{name}_pthermal_var")
        mock_builder_instance.phydro = MagicMock(name=f"{name}_phydro_var")
        mock_builder_instance.psolar = MagicMock(name=f"{name}_psolar_var")
        mock_builder_instance.pwind = MagicMock(name=f"{name}_pwind_var")
        mock_builder_instance.pimp = MagicMock(name=f"{name}_pimp_var")
        mock_builder_instance.pcharge = MagicMock(name=f"{name}_pcharge_var")
        mock_builder_instance.pdischarge = MagicMock(name=f"{name}_pdischarge_var")
        mock_builder_instance.charge_state = MagicMock(name=f"{name}_charge_state_var")
        return mock_builder_instance

    # Arguments are in reverse order of decorators (SystemInput is MockSystemInput etc.)
    def test_initialization(
        self,
        MockSystemInput,  # Corresponds to @patch(f"{PATCH_BASE}.SystemInput")
        MockGPModel,  # Corresponds to @patch(f"{PATCH_BASE}.gp.Model")
        MockGPLinExpr,  # Corresponds to @patch(f"{PATCH_BASE}.gp.LinExpr")
        MockPowerSystemModel,  # Corresponds to @patch(f"{PATCH_BASE}.PowerSystemModel")
        MockThermalBuilder,
        MockHydroBuilder,
        MockNonDispatchBuilder,
        MockStorageBuilder,
        MockSystemBuilder,  # Corresponds to @patch(f"{PATCH_BASE}.SystemBuilder")
    ):
        mock_inputs = MockSystemInput(
            input_folder="dummy_path",
            model_name="test_model",
            year=2025,
            sim_horizon=24,
        )
        mock_inputs.model_id = "test_model_123"

        # Instantiate ModelBuilder
        # This will use the mocked versions of SystemInput, gp.Model, gp.LinExpr etc.
        # from within pownet.model_builder's scope.
        model_builder = ModelBuilder(inputs=mock_inputs)

        # Assert Gurobi Model initialization (gp.Model)
        MockGPModel.assert_called_once_with("test_model_123")
        self.assertEqual(model_builder.model, MockGPModel.return_value)

        # Assert LinExpr initialization for total_fixed_objective_expr (gp.LinExpr)
        # The side_effect of MockGPLinExpr is a lambda creating MockLinExpr instances.
        # It should be called once in ModelBuilder.__init__
        MockGPLinExpr.assert_called_once_with()
        self.assertIsInstance(model_builder.total_fixed_objective_expr, MockLinExpr)
        self.assertEqual(model_builder.total_fixed_objective_expr.value, 0.0)

        # Assert sub-builders instantiation
        MockThermalBuilder.assert_called_once_with(model_builder.model, mock_inputs)
        MockHydroBuilder.assert_called_once_with(model_builder.model, mock_inputs)
        MockNonDispatchBuilder.assert_called_once_with(model_builder.model, mock_inputs)
        MockStorageBuilder.assert_called_once_with(model_builder.model, mock_inputs)
        MockSystemBuilder.assert_called_once_with(model_builder.model, mock_inputs)

        self.assertEqual(model_builder.thermal_builder, MockThermalBuilder.return_value)
        self.assertEqual(model_builder.hydro_builder, MockHydroBuilder.return_value)
        # ... and so on for other builders

    def test_build_model(
        self,
        MockSystemInput,
        MockGPModel,
        MockGPLinExpr,
        MockPowerSystemModel,
        MockThermalBuilder,
        MockHydroBuilder,
        MockNonDispatchBuilder,
        MockStorageBuilder,
        MockSystemBuilder,
    ):
        mock_inputs = MockSystemInput(
            input_folder="dummy_path",
            model_name="test_model",
            year=2025,
            sim_horizon=24,
        )
        mock_inputs.model_id = "build_test"

        # Reset LinExpr mock for this test to ensure fresh naming if needed,
        # or ensure the side_effect lambda is fresh for each call.
        # The current side_effect lambda already gives fresh instances.
        # MockGPLinExpr.side_effect = lambda name_suffix="": MockLinExpr(0.0, f"build_LinExpr_{name_suffix}")

        model_builder = ModelBuilder(inputs=mock_inputs)
        mock_gurobi_model_instance = (
            MockGPModel.return_value
        )  # Instance from ModelBuilder.__init__

        # Configure mock builders
        mock_thermal_inst = self._configure_mock_builder(
            MockThermalBuilder.return_value, "thermal", 1, 10
        )
        mock_hydro_inst = self._configure_mock_builder(
            MockHydroBuilder.return_value, "hydro", 2, 20
        )
        mock_nondispatch_inst = self._configure_mock_builder(
            MockNonDispatchBuilder.return_value, "nondispatch", 3, 30
        )
        mock_storage_inst = self._configure_mock_builder(
            MockStorageBuilder.return_value, "storage", 4, 40
        )
        mock_system_inst = self._configure_mock_builder(
            MockSystemBuilder.return_value, "system", 5, 50
        )

        step_k = 1
        init_conds = {"some_unit": {"status": 1}}

        returned_model = model_builder.build(step_k, init_conds)

        mock_thermal_inst.add_variables.assert_called_once_with(step_k=step_k)
        mock_hydro_inst.add_variables.assert_called_once_with(step_k=step_k)
        mock_nondispatch_inst.add_variables.assert_called_once_with(step_k=step_k)
        mock_storage_inst.add_variables.assert_called_once_with(step_k=step_k)
        mock_system_inst.add_variables.assert_called_once_with(step_k=step_k)

        mock_thermal_inst.get_fixed_objective_terms.assert_called_once_with()
        mock_hydro_inst.get_fixed_objective_terms.assert_called_once_with()
        # ... (assert for all fixed objective term getters)

        mock_thermal_inst.get_variable_objective_terms.assert_called_once_with(
            step_k=step_k
        )
        mock_hydro_inst.get_variable_objective_terms.assert_called_once_with(
            step_k=step_k
        )
        # ... (assert for all variable objective term getters)

        self.assertEqual(
            model_builder.total_fixed_objective_expr.value, 1.0 + 2.0 + 3.0 + 4.0 + 5.0
        )  # 15.0

        args, kwargs = mock_gurobi_model_instance.setObjective.call_args
        self.assertIsInstance(args[0], MockLinExpr)
        self.assertEqual(
            args[0].value, 15.0 + (10.0 + 20.0 + 30.0 + 40.0 + 50.0)
        )  # 165.0
        self.assertEqual(kwargs["sense"], GRB.MINIMIZE)

        mock_thermal_inst.add_constraints.assert_called_once_with(
            step_k=step_k, init_conds=init_conds
        )
        # ... (assert add_constraints for other builders)
        mock_system_inst.add_constraints.assert_called_once_with(
            step_k=step_k,
            init_conds=init_conds,
            spin_vars=mock_thermal_inst.spin,
            vpowerbar_vars=mock_thermal_inst.vpowerbar,
            thermal_status_vars=mock_thermal_inst.status,
            pthermal=mock_thermal_inst.pthermal,
            phydro=mock_hydro_inst.phydro,
            psolar=mock_nondispatch_inst.psolar,
            pwind=mock_nondispatch_inst.pwind,
            pimp=mock_nondispatch_inst.pimp,
            pcharge=mock_storage_inst.pcharge,
            pdischarge=mock_storage_inst.pdischarge,
            charge_state=mock_storage_inst.charge_state,
        )

        mock_gurobi_model_instance.update.assert_called_once_with()
        MockPowerSystemModel.assert_called_once_with(mock_gurobi_model_instance)
        self.assertEqual(returned_model, MockPowerSystemModel.return_value)

    def test_update_model(
        self,
        MockSystemInput,
        MockGPModel,
        MockGPLinExpr,
        MockPowerSystemModel,
        MockThermalBuilder,
        MockHydroBuilder,
        MockNonDispatchBuilder,
        MockStorageBuilder,
        MockSystemBuilder,
    ):
        mock_inputs = MockSystemInput(
            input_folder="dummy_path",
            model_name="test_model",
            year=2025,
            sim_horizon=24,
        )
        mock_inputs.model_id = "update_test"

        # MockGPLinExpr.side_effect = lambda name_suffix="": MockLinExpr(0.0, f"update_LinExpr_{name_suffix}")

        model_builder = ModelBuilder(inputs=mock_inputs)
        mock_gurobi_model_instance = MockGPModel.return_value

        mock_thermal_inst = self._configure_mock_builder(
            MockThermalBuilder.return_value, "thermal", 1, 10
        )
        mock_hydro_inst = self._configure_mock_builder(
            MockHydroBuilder.return_value, "hydro", 2, 20
        )
        mock_nondispatch_inst = self._configure_mock_builder(
            MockNonDispatchBuilder.return_value, "nondispatch", 3, 30
        )
        mock_storage_inst = self._configure_mock_builder(
            MockStorageBuilder.return_value, "storage", 4, 40
        )
        mock_system_inst = self._configure_mock_builder(
            MockSystemBuilder.return_value, "system", 5, 50
        )

        # Manually set the fixed objective part as if build() or a previous state set it.
        # In ModelBuilder, total_fixed_objective_expr is accumulated in build().
        # For update(), it relies on this being pre-populated.
        # Here, we simulate it being populated from a previous build() or state.
        # The __init__ already creates one via MockGPLinExpr, let's assume it was 0.
        # If build() ran, it would sum up actual fixed terms.
        # For this test, we'll set it to a known sum.
        model_builder.total_fixed_objective_expr = MockLinExpr(
            1.0 + 2.0 + 3.0 + 4.0 + 5.0, "fixed_sum_pre_update"
        )  # 15.0

        step_k_update = 2
        init_conds_update = {"some_unit": {"status": 0}}

        # Update variable objective term mocks for the update call
        mock_thermal_inst.get_variable_objective_terms.return_value = MockLinExpr(
            11, "thermal_var_updated"
        )
        mock_hydro_inst.get_variable_objective_terms.return_value = MockLinExpr(
            22, "hydro_var_updated"
        )
        mock_nondispatch_inst.get_variable_objective_terms.return_value = MockLinExpr(
            33, "nondispatch_var_updated"
        )
        mock_storage_inst.get_variable_objective_terms.return_value = MockLinExpr(
            44, "storage_var_updated"
        )
        mock_system_inst.get_variable_objective_terms.return_value = MockLinExpr(
            55, "system_var_updated"
        )

        returned_model = model_builder.update(step_k_update, init_conds_update)

        mock_thermal_inst.update_variables.assert_called_once_with(step_k=step_k_update)
        # ... (assert update_variables for others)

        # Check setObjective was called for the update
        # The call count for setObjective might be tricky if build() was also called in a way that sets it.
        # Let's focus on the arguments of the *last* call to setObjective if it's called multiple times.
        # Or, if ModelBuilder.__init__ doesn't set objective, then it's 1.
        # ModelBuilder.update() *does* call setObjective.
        self.assertEqual(
            mock_gurobi_model_instance.setObjective.call_count, 1
        )  # Assuming __init__ doesn't call it, only build/update

        args, kwargs = mock_gurobi_model_instance.setObjective.call_args
        self.assertIsInstance(args[0], MockLinExpr)
        # Fixed (15.0) + New variable (11+22+33+44+55 = 165.0) = 180.0
        self.assertEqual(args[0].value, 15.0 + 165.0)
        self.assertEqual(kwargs["sense"], GRB.MINIMIZE)

        mock_thermal_inst.get_variable_objective_terms.assert_called_with(
            step_k=step_k_update
        )
        # ... (assert get_variable_objective_terms for others)

        mock_system_inst.update_constraints.assert_called_once_with(
            step_k=step_k_update,
            init_conds=init_conds_update,
            spin_vars=mock_thermal_inst.spin,
            vpowerbar_vars=mock_thermal_inst.vpowerbar,
            thermal_status_vars=mock_thermal_inst.status,
            pthermal=mock_thermal_inst.pthermal,
            phydro=mock_hydro_inst.phydro,
            psolar=mock_nondispatch_inst.psolar,
            pwind=mock_nondispatch_inst.pwind,
            pimp=mock_nondispatch_inst.pimp,
            pcharge=mock_storage_inst.pcharge,
            pdischarge=mock_storage_inst.pdischarge,
            charge_state=mock_storage_inst.charge_state,
        )
        # model.update() is called in update()
        self.assertEqual(mock_gurobi_model_instance.update.call_count, 1)

        MockPowerSystemModel.assert_called_with(mock_gurobi_model_instance)
        self.assertEqual(returned_model, MockPowerSystemModel.return_value)

    def test_get_phydro(
        self,
        MockSystemInput,
        MockGPModel,
        MockGPLinExpr,
        MockPowerSystemModel,
        MockThermalBuilder,
        MockHydroBuilder,
        MockNonDispatchBuilder,
        MockStorageBuilder,
        MockSystemBuilder,
    ):
        mock_inputs = MockSystemInput(
            input_folder="dummy_path",
            model_name="test_model",
            year=2025,
            sim_horizon=24,
        )
        mock_inputs.model_id = "get_phydro_test_model"

        model_builder = ModelBuilder(inputs=mock_inputs)  # This will use mocked gp

        mock_hydro_inst = MockHydroBuilder.return_value
        expected_phydro = MagicMock(name="phydro_var_dict")
        mock_hydro_inst.phydro = (
            expected_phydro  # Set the attribute on the mock instance
        )

        phydro_vars = model_builder.get_phydro()
        self.assertEqual(phydro_vars, expected_phydro)

    def test_update_daily_hydropower_capacity(
        self,
        MockSystemInput,
        MockGPModel,
        MockGPLinExpr,
        MockPowerSystemModel,
        MockThermalBuilder,
        MockHydroBuilder,
        MockNonDispatchBuilder,
        MockStorageBuilder,
        MockSystemBuilder,
    ):
        mock_inputs = MockSystemInput(
            input_folder="dummy_path",
            model_name="test_model",
            year=2023,
            sim_horizon=24,
        )
        mock_inputs.model_id = "update_hydro_cap_model"

        model_builder = ModelBuilder(inputs=mock_inputs)
        mock_gurobi_model_instance = MockGPModel.return_value
        mock_hydro_inst = MockHydroBuilder.return_value

        step_k = 5
        new_capacity = {("H1", 0): 100.0, ("H2", 0): 50.0}

        returned_model = model_builder.update_daily_hydropower_capacity(
            step_k, new_capacity
        )

        mock_hydro_inst.update_daily_hydropower_capacity.assert_called_once_with(
            step_k, new_capacity
        )
        mock_gurobi_model_instance.update.assert_called_once_with()
        MockPowerSystemModel.assert_called_once_with(mock_gurobi_model_instance)
        self.assertEqual(returned_model, MockPowerSystemModel.return_value)


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
