# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines load zone parameters for the SWITCH-Pyomo model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel('timescales', 'load_zones')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""
import os
from pyomo.environ import *


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters that
    describe load zones and some related geographic areas. Unless
    otherwise stated, each set and parameter is mandatory.

    LOAD_ZONES is the set of load zones. mod uses a zonal
    transport model to describe the power grid. Each zone is effectively
    modeled as a single bus connected to the inter-zonal transmission
    network, and connected to loads via local transmission and
    distribution that incurs efficiency losses and must be upgraded over
    time to always meet peak demand. Load zones are abbreviated as lz in
    parameter names and as z for indexes.

    lz_demand_mw[z,t] describes the average power demand in each load
    zone z and timepoint t. This is a non negative value.

    lz_demand_mw_as_consumption[z,t] is the same as lz_demand_mw but
    with a negative sign for the benefit of energy balancing equations.

    lz_dbid[z] stores an external database id for each load zone. This
    is optional and defaults to the name of the load zone. It will be
    printed out when results are exported.

    lz_cost_multipliers[z] is an zone-specific economic multiplier that
    modifies all costs incurred in each load zone. This could reflect
    differential costs of labor, regional inflation, etc. This is an
    optional parameter with a default of 1. mod-WECC uses values
    from the Army Corps of Engineers Civil Works Construction Cost Index
    System with values ranging from 0.92 to 1.20.

    lz_ccs_distance_km[z] describes the length of a pipeline in
    kilometers that would need to be built to transport CO2 from a load
    zones central bus to the nearest viable CCS reservoir. This
    parameter is optional unless Carbon Capture and Sequestration
    technologies is enabled.

    DumpPower[load_zone, timepoint] is a decision variable that allows
    overproduction of energy in every load zone and timepoint.
    This may be interpretted either as the aggregate curtailment needed,
    or as a literal dump load. In the language of linear programming,
    this is a "slack variable" for an energy balancing constraint.

    LZ_Energy_Balance_components is a list of components that contribute
    to load-zone level energy balance equations. Other modules may add
    elements to this list. The energy_balance module will construct a
    Satisfy_Load constraint using this list. Each component in this list
    needs to be indexed by [load_zone, timepoint]. If this indexing is
    not convenient for native model components, I advise writing an
    Expression object indexed by [lz,t] that contains logic to access or
    summarize native model components.

    Derived parameters:

    lz_total_demand_in_period_mwh[z,p] describes the total energy demand
    of each load zone in each period in Megawatt hours.

    """

    mod.LOAD_ZONES = Set()
    mod.lz_demand_mw = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonNegativeReals)
    mod.lz_cost_multipliers = Param(
        mod.LOAD_ZONES,
        within=PositiveReals,
        default=1.0)
    mod.lz_ccs_distance_km = Param(
        mod.LOAD_ZONES,
        within=NonNegativeReals)
    mod.lz_dbid = Param(
        mod.LOAD_ZONES,
        default=lambda m, lz: lz)
    # Verify that mandatory data exists before using it.
    mod.min_data_check('LOAD_ZONES', 'lz_demand_mw')
    mod.lz_total_demand_in_period_mwh = Param(
        mod.LOAD_ZONES, mod.PERIODS,
        within=PositiveReals,
        initialize=lambda m, z, p: (
            sum(m.lz_demand_mw[z, t] * m.tp_weight[t]
                for t in m.PERIOD_TPS[p])))
    mod.lz_demand_mw_as_consumption = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=lambda m, lz, t: -1 * m.lz_demand_mw[lz, t])
    mod.DumpPower = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonPositiveReals)
    mod.LZ_Energy_Balance_components = [
        'lz_demand_mw_as_consumption', 'DumpPower']


def define_dynamic_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of load zone busses. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Energy_Balance[load_zone, timepoint] is a constraint that mandates
    conservation of energy in every load zone and timepoint. This
    constraint sums the model components in the list
    LZ_Energy_Balance_components - each of which is indexed by (lz, t) -
    and ensures they sum to 0. By convention, energy production has a
    positive sign and energy consumption has a negative sign.

    """

    mod.Energy_Balance = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, lz, t: sum(
            getattr(m, component)[lz, t]
            for component in m.LZ_Energy_Balance_components
        ) == 0)


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import load zone data. The following tab-separated files are
    expected in the input directory. Their columns can be in any order,
    and any extra columns will be ignored during import. If you don't
    want to specify data for any optional parameter, use a dot . for its
    value.

    load_zones.tab
        LOAD_ZONE, cost_multipliers, ccs_distance_km, dbid

    loads.tab
        LOAD_ZONE, TIMEPOINT, demand_mw

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'load_zones.tab'),
        select=('LOAD_ZONE', 'cost_multipliers', 'ccs_distance_km',
                'dbid'),
        index=mod.LOAD_ZONES,
        param=(mod.lz_cost_multipliers, mod.lz_ccs_distance_km,
               mod.lz_dbid))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'loads.tab'),
        select=('LOAD_ZONE', 'TIMEPOINT', 'demand_mw'),
        param=(mod.lz_demand_mw))


def save_results(model, instance, outdir):
    """
    Export results to standard files.

    This initial placeholder version is integrating snippets of
    some of Matthias's code into the main codebase.

    """
    import switch_mod.export as export
    export.write_table(
        instance, instance.TIMEPOINTS,
        output_file=os.path.join("outputs", "load_balance.txt"),
        headings=("timestamp",) + tuple(
            instance.LZ_Energy_Balance_components),
        values=lambda m, t: (m.tp_timestamp[t],) + tuple(
            sum(getattr(m, component)[lz, t] for lz in m.LOAD_ZONES)
            for component in m.LZ_Energy_Balance_components
        )
    )
