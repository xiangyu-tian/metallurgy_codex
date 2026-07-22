"""Build the materialized Metallurgy Platform v2.0 numerical benchmark.

Expected values are calculated from independent analytical reference formulas
and the frozen IUPAC/NIST constants, not by invoking the model registry.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter


TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, TOOLS_DIR)

from models_core.chemical_data import SHOMATE_PARAMS, THERMOCHEMICAL_DB


ATOMIC_WEIGHTS = {
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "S": 32.06,
    "Ca": 40.078, "Mn": 54.938, "Fe": 55.845,
}


def shomate(species: str, temperature: float) -> dict:
    p = SHOMATE_PARAMS[species]
    t = temperature / 1000.0
    cp = p["A"] + p["B"] * t + p["C"] * t**2 + p["D"] * t**3 + p["E"] / t**2
    enthalpy = (
        p["A"] * t + p["B"] * t**2 / 2 + p["C"] * t**3 / 3
        + p["D"] * t**4 / 4 - p["E"] / t + p["F"] - p["H"]
    )
    entropy = (
        p["A"] * math.log(t) + p["B"] * t + p["C"] * t**2 / 2
        + p["D"] * t**3 / 3 - p["E"] / (2 * t**2) + p["G"]
    )
    return {"cp": cp, "enthalpy": enthalpy, "entropy": entropy}


def add_case(cases, model_code, inputs, path, value, reference, *, abs_tol=0.0, rel_tol=0.0):
    sequence = sum(1 for case in cases if case["model_code"] == model_code) + 1
    tolerance = {}
    if abs_tol:
        tolerance["abs"] = abs_tol
    if rel_tol:
        tolerance["rel"] = rel_tol
    cases.append({
        "case_id": f"G-{model_code}-{sequence:03d}",
        "model_code": model_code,
        "input": inputs,
        "expected": {"path": path, "value": value},
        "tolerance": tolerance,
        "reference": reference,
        "applicable_conditions": "输入位于模型卡声明的适用域内",
        "should_reject": False,
    })


def build_cases():
    cases = []

    conversions = [
        (1000, "kg", "t", 1), (2.5, "t", "kg", 2500),
        (750, "g", "kg", 0.75), (1, "km", "m", 1000),
        (250, "cm", "m", 2.5), (25, "mm", "cm", 2.5),
        (1, "MPa", "kPa", 1000), (2, "bar", "Pa", 200000),
        (1, "atm", "Pa", 101325), (25, "°C", "K", 298.15),
        (373.15, "K", "°C", 100), (2, "h", "min", 120),
    ]
    for value, source, target, expected in conversions:
        add_case(cases, "A001", {"value": value, "source_unit": source, "target_unit": target},
                 "value", expected, "SI/NIST unit conversion", abs_tol=1e-9)

    formulas = [
        ("Fe2O3", {"Fe": 2, "O": 3}), ("Fe3O4", {"Fe": 3, "O": 4}),
        ("CaCO3", {"Ca": 1, "C": 1, "O": 3}), ("Al2O3", {"Al": 2, "O": 3}),
        ("SiO2", {"Si": 1, "O": 2}), ("MgO", {"Mg": 1, "O": 1}),
        ("MnO", {"Mn": 1, "O": 1}), ("Si3N4", {"Si": 3, "N": 4}),
        ("Ca(OH)2", {"Ca": 1, "O": 2, "H": 2}),
        ("Fe2(SO4)3", {"Fe": 2, "S": 3, "O": 12}),
    ]
    for formula, elements in formulas:
        add_case(cases, "A002", {"formula": formula}, "total_atoms", sum(elements.values()),
                 "Chemical stoichiometry", abs_tol=0)
    for formula, elements in formulas:
        mass = sum(ATOMIC_WEIGHTS[element] * count for element, count in elements.items())
        add_case(cases, "A003", {"formula": formula}, "molar_mass", round(mass, 4),
                 "IUPAC 2021 atomic weights", abs_tol=0.0001)

    compositions = [
        {"Fe": 94, "C": 4, "Si": 2}, {"Fe": 0.98, "C": 0.02},
        {"CaO": 45, "SiO2": 35, "Al2O3": 20}, {"CO": 2, "CO2": 3},
        {"FeO": 72, "Fe2O3": 18, "SiO2": 10}, {"Ni": 8, "Cr": 18, "Fe": 74},
        {"C": 1, "O": 4}, {"H2": 3, "N2": 1},
    ]
    for comp in compositions:
        first = next(iter(comp))
        expected = round(comp[first] / sum(comp.values()), 6)
        add_case(cases, "A004", {"compositions": comp}, f"normalized.{first}", expected,
                 "Composition normalization identity", abs_tol=1e-6)

    for index, mass in enumerate((10, 25, 50, 100, 250, 1000), start=1):
        fractions = {"Fe": 0.96, "C": 0.03, "Si": 0.01}
        inputs = [{"name": f"feed-{index}", "mass": mass, "elements": fractions}]
        outputs = [{"name": f"product-{index}", "mass": mass, "elements": fractions}]
        add_case(cases, "A005", {"input_streams": inputs, "output_streams": outputs},
                 "mass_closure_rate", 1.0, "Mass conservation identity", abs_tol=1e-12)

    thermo_points = [
        ("Fe(s)", 298.15), ("Fe(s)", 700), ("Fe(s)", 1000),
        ("O2(g)", 500), ("O2(g)", 1000), ("CO2(g)", 600),
        ("FeO(s)", 900), ("CaO(s)", 1200),
    ]
    for species, temperature in thermo_points:
        expected = shomate(species, temperature)["cp"]
        add_case(cases, "B001", {"species": species, "temperature": temperature},
                 "Cp", round(expected, 6), "NIST Shomate equation", abs_tol=1e-5)
    for species, temperature in thermo_points[:6]:
        expected = shomate(species, temperature)["cp"]
        add_case(cases, "B002", {"species": species, "temperature": temperature},
                 "Cp", round(expected, 6), "NIST Shomate equation used as NASA approximation", abs_tol=1e-5)

    enthalpy_ranges = [
        ("Fe(s)", 298.15, 600), ("Fe(s)", 400, 1000),
        ("O2(g)", 298.15, 800), ("O2(g)", 500, 1500),
        ("CO2(g)", 298.15, 700), ("FeO(s)", 400, 1200),
        ("CaO(s)", 500, 1500), ("Al2O3(s,alpha)", 600, 1800),
    ]
    for species, start, end in enthalpy_ranges:
        expected = shomate(species, end)["enthalpy"] - shomate(species, start)["enthalpy"]
        add_case(cases, "B003", {"species": species, "temperature_start": start, "temperature_end": end},
                 "delta_H", round(expected, 4), "Analytical Shomate enthalpy difference", abs_tol=0.002)

    for species, start, end in enthalpy_ranges[:6]:
        expected = shomate(species, end)["entropy"] - shomate(species, start)["entropy"]
        add_case(cases, "B004", {"species": species, "temperature_start": start, "temperature_end": end},
                 "delta_S", round(expected, 4), "Analytical Shomate entropy difference", abs_tol=0.0002)

    for species, temperature in thermo_points[:6]:
        point = shomate(species, temperature)
        expected = point["enthalpy"] - temperature * point["entropy"] / 1000.0
        add_case(cases, "B005", {"species": species, "temperature": temperature},
                 "G", round(expected, 4), "G = H - TS using NIST Shomate properties", abs_tol=0.0001)

    reactions = THERMOCHEMICAL_DB[:6]
    for reaction in reactions:
        add_case(cases, "B006", {"reaction": reaction["reaction"], "temperature": 298.15},
                 "delta_H", reaction["deltaH"], "NIST-JANAF reaction enthalpy", abs_tol=0.1)
        add_case(cases, "B007", {"reaction": reaction["reaction"], "temperature": 298.15},
                 "delta_S", reaction["deltaS"], "NIST-JANAF reaction entropy", abs_tol=0.1)

    gibbs_points = [
        (THERMOCHEMICAL_DB[0], 500), (THERMOCHEMICAL_DB[0], 1000),
        (THERMOCHEMICAL_DB[1], 800), (THERMOCHEMICAL_DB[2], 1200),
        (THERMOCHEMICAL_DB[3], 900), (THERMOCHEMICAL_DB[4], 1100),
        (THERMOCHEMICAL_DB[5], 900), (THERMOCHEMICAL_DB[5], 1200),
    ]
    for reaction, temperature in gibbs_points:
        delta_g = reaction["deltaH"] - temperature * reaction["deltaS"] / 1000.0
        add_case(cases, "B008", {"reaction": reaction["reaction"], "temperature": temperature},
                 "delta_G", round(delta_g, 2), "Delta G = Delta H - T Delta S", abs_tol=0.01)
        log10_k = -delta_g * 1000.0 / (8.314 * temperature * math.log(10))
        add_case(cases, "B009", {"reaction": reaction["reaction"], "temperature": temperature},
                 "log10_K", round(log10_k, 4), "ln K = -Delta G/(RT)", abs_tol=0.0001)

    lever_points = [
        (0.2, 0.1, 0.5), (0.3, 0.1, 0.5), (0.4, 0.2, 0.8),
        (0.5, 0.0, 1.0), (0.6, 0.4, 0.9), (0.7, 0.2, 0.8),
        (10, 5, 25), (25, 10, 40), (60, 20, 80), (90, 85, 95),
    ]
    for overall, phase1, phase2 in lever_points:
        expected = (overall - phase1) / (phase2 - phase1)
        add_case(cases, "B019", {"overall_composition": overall, "phase1_composition": phase1, "phase2_composition": phase2},
                 "phase2_fraction", round(expected, 6), "Binary lever rule", abs_tol=1e-6)

    arrhenius_points = [
        (1e7, 80000, 800, "J/mol"), (1e7, 80000, 1000, "J/mol"),
        (2e9, 120, 1200, "kJ/mol"), (5e6, 60, 900, "kJ/mol"),
        (1e12, 180000, 1500, "J/mol"), (3e8, 95, 1100, "kJ/mol"),
        (9e5, 40, 700, "kJ/mol"), (7e10, 140000, 1300, "J/mol"),
        (4e4, 25, 600, "kJ/mol"), (6e11, 200, 1800, "kJ/mol"),
    ]
    for pre_factor, energy, temperature, unit in arrhenius_points:
        energy_j = energy * 1000 if unit == "kJ/mol" else energy
        expected = pre_factor * math.exp(-energy_j / (8.314 * temperature))
        add_case(cases, "C001", {"A": pre_factor, "Ea": energy, "temperature": temperature, "Ea_unit": unit},
                 "k", round(expected, 10), "Arrhenius analytical solution", rel_tol=1e-9, abs_tol=1e-10)

    diffusion_points = [
        (1e-4, 40000, 800), (1e-4, 60000, 1000), (2e-5, 50000, 1200),
        (5e-4, 80000, 1400), (1e-3, 90000, 1600), (8e-5, 30000, 700),
        (3e-6, 45000, 900), (2e-4, 70000, 1300), (7e-5, 55000, 1100),
        (9e-4, 100000, 1800),
    ]
    for d0, energy, temperature in diffusion_points:
        expected = d0 * math.exp(-energy / (8.314 * temperature))
        add_case(cases, "C002", {"D0": d0, "Q": energy, "temperature": temperature, "Q_unit": "J/mol"},
                 "D", round(expected, 12), "Diffusion Arrhenius analytical solution", abs_tol=1e-12)

    return cases


def build_dataset():
    cases = build_cases()
    coverage = Counter(case["model_code"] for case in cases)
    return {
        "baseline_version": "2.0.0",
        "reference_policy": "Independent analytical equations with frozen IUPAC 2021 and NIST-JANAF/Shomate constants",
        "case_count": len(cases),
        "model_coverage": dict(sorted(coverage.items())),
        "cases": cases,
    }


def main():
    output_path = os.path.join(os.path.dirname(__file__), "golden_cases.json")
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(build_dataset(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"wrote {output_path} with {len(build_cases())} cases")


if __name__ == "__main__":
    main()
