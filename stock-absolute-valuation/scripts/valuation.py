#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自由现金流贴现模型估值计算器

支持：零增长(zero)、永续增长(perpetuity)、两阶段(two-stage)、三阶段(three-stage)
"""
import argparse
import json
import sys


def parse_rate(s: str) -> float:
    """接受 0.15 或 15% 两种写法"""
    s = s.strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s)


def fmt(x: float) -> str:
    return f"{x:,.2f}"


def zero_growth(fcf0, r):
    if r <= 0:
        raise ValueError("零增长模型要求 r > 0")
    v = fcf0 / r
    return {
        "model": "零增长模型",
        "formula": "V = FCF / r",
        "steps": [f"V = {fmt(fcf0)} / {r:.4f} = {fmt(v)}"],
        "value": v,
    }


def perpetuity(fcf0, r, g):
    if r <= g:
        raise ValueError(f"永续增长模型要求 r > g（当前 r={r}, g={g}），否则估值发散")
    v = fcf0 * (1 + g) / (r - g)
    return {
        "model": "永续增长模型",
        "formula": "V = FCF₀ × (1+g) / (r-g)",
        "steps": [
            f"FCF₁ = {fmt(fcf0)} × (1+{g}) = {fmt(fcf0 * (1 + g))}",
            f"V = {fmt(fcf0 * (1 + g))} / ({r} - {g}) = {fmt(v)}",
        ],
        "value": v,
    }


def two_stage(fcf0, r, g1, g2, n):
    if r <= g2:
        raise ValueError(f"两阶段模型要求 r > g₂（当前 r={r}, g₂={g2}），否则终值发散")

    steps = []
    pv1_total = 0.0
    rows = []
    for t in range(1, n + 1):
        fcf_t = fcf0 * (1 + g1) ** t
        df = 1 / (1 + r) ** t
        pv = fcf_t * df
        pv1_total += pv
        rows.append({
            "t": t,
            "fcf": round(fcf_t, 2),
            "discount_factor": round(df, 6),
            "pv": round(pv, 2),
        })
        steps.append(
            f"第{t}年: FCF = {fmt(fcf0)}×(1+{g1})^{t} = {fmt(fcf_t)}, "
            f"折现因子 = 1/(1+{r})^{t} = {df:.6f}, 现值 = {fmt(pv)}"
        )

    fcf_n = fcf0 * (1 + g1) ** n
    tv = fcf_n * (1 + g2) / (r - g2)
    pv_tv = tv / (1 + r) ** n
    steps.append(f"终值 TV = FCF_n×(1+g₂)/(r-g₂) = {fmt(fcf_n)}×(1+{g2})/({r}-{g2}) = {fmt(tv)}")
    steps.append(f"终值现值 = {fmt(tv)} / (1+{r})^{n} = {fmt(pv_tv)}")

    v = pv1_total + pv_tv
    steps.append(f"V = 第一阶段现值合计 {fmt(pv1_total)} + 终值现值 {fmt(pv_tv)} = {fmt(v)}")

    return {
        "model": "两阶段模型",
        "formula": "V = Σ FCF₀(1+g₁)^t/(1+r)^t + FCF_n(1+g₂)/[(r-g₂)(1+r)^n]",
        "params": {"FCF0": fcf0, "r": r, "g1": g1, "g2": g2, "n": n},
        "yearly": rows,
        "stage1_pv": round(pv1_total, 2),
        "terminal_value": round(tv, 2),
        "terminal_value_pv": round(pv_tv, 2),
        "steps": steps,
        "value": round(v, 2),
    }


def three_stage(fcf0, r, g1, g2, g3, n, m):
    # m 为第二阶段结束的年份（总年数），n 为第一阶段年数
    if r <= g3:
        raise ValueError(f"三阶段模型要求 r > g₃（当前 r={r}, g₃={g3}），否则终值发散")

    steps = []
    rows = []
    pv_total = 0.0
    fcf_prev = fcf0

    # 阶段1：成长期 t=1..n，增长 g1
    for t in range(1, n + 1):
        fcf_t = fcf_prev * (1 + g1)
        df = 1 / (1 + r) ** t
        pv = fcf_t * df
        pv_total += pv
        rows.append({"t": t, "stage": 1, "g": g1, "fcf": round(fcf_t, 2),
                     "discount_factor": round(df, 6), "pv": round(pv, 2)})
        steps.append(f"第{t}年(成长): FCF = {fmt(fcf_t)}, 折现因子 = {df:.6f}, 现值 = {fmt(pv)}")
        fcf_prev = fcf_t
    pv_stage1 = pv_total

    # 阶段2：过渡期 t=n+1..m，增长 g2
    for t in range(n + 1, m + 1):
        fcf_t = fcf_prev * (1 + g2)
        df = 1 / (1 + r) ** t
        pv = fcf_t * df
        pv_total += pv
        rows.append({"t": t, "stage": 2, "g": g2, "fcf": round(fcf_t, 2),
                     "discount_factor": round(df, 6), "pv": round(pv, 2)})
        steps.append(f"第{t}年(过渡): FCF = {fmt(fcf_t)}, 折现因子 = {df:.6f}, 现值 = {fmt(pv)}")
        fcf_prev = fcf_t
    pv_stage2 = pv_total - pv_stage1

    # 阶段3：稳定期终值
    fcf_m = fcf_prev
    tv = fcf_m * (1 + g3) / (r - g3)
    pv_tv = tv / (1 + r) ** m
    steps.append(f"终值 TV = FCF_m×(1+g₃)/(r-g₃) = {fmt(fcf_m)}×(1+{g3})/({r}-{g3}) = {fmt(tv)}")
    steps.append(f"终值现值 = {fmt(tv)} / (1+{r})^{m} = {fmt(pv_tv)}")

    v = pv_total + pv_tv
    steps.append(f"V = 成长期现值 {fmt(pv_stage1)} + 过渡期现值 {fmt(pv_stage2)} + 终值现值 {fmt(pv_tv)} = {fmt(v)}")

    return {
        "model": "三阶段模型",
        "formula": "V = Σ₁ⁿ FCF₀(1+g₁)^t/(1+r)^t + Σₙ₊₁ᵐ FCF_n(1+g₂)^(t-n)/(1+r)^t + FCF_m(1+g₃)/[(r-g₃)(1+r)^m]",
        "params": {"FCF0": fcf0, "r": r, "g1": g1, "g2": g2, "g3": g3, "n": n, "m": m},
        "yearly": rows,
        "stage1_pv": round(pv_stage1, 2),
        "stage2_pv": round(pv_stage2, 2),
        "terminal_value": round(tv, 2),
        "terminal_value_pv": round(pv_tv, 2),
        "steps": steps,
        "value": round(v, 2),
    }


def main():
    p = argparse.ArgumentParser(description="自由现金流贴现模型估值")
    p.add_argument("model", choices=["zero", "perpetuity", "two-stage", "three-stage"])
    p.add_argument("--fcf0", type=float, required=True, help="基期自由现金流")
    p.add_argument("--r", type=parse_rate, required=True, help="折现率（0.08 或 8%%）")
    p.add_argument("--g", type=parse_rate, help="永续增长率")
    p.add_argument("--g1", type=parse_rate, help="第一阶段增长率")
    p.add_argument("--g2", type=parse_rate, help="第二阶段增长率")
    p.add_argument("--g3", type=parse_rate, help="第三阶段增长率")
    p.add_argument("--n", type=int, help="第一阶段年数")
    p.add_argument("--m", type=int, help="三阶段：第二阶段结束年份（总年数）")
    p.add_argument("--unit", default="", help="金额单位（如 万元/亿元），仅用于展示")
    args = p.parse_args()

    try:
        if args.model == "zero":
            result = zero_growth(args.fcf0, args.r)
        elif args.model == "perpetuity":
            if args.g is None:
                sys.exit("错误：永续增长模型需要 --g")
            result = perpetuity(args.fcf0, args.r, args.g)
        elif args.model == "two-stage":
            if None in (args.g1, args.g2, args.n):
                sys.exit("错误：两阶段模型需要 --g1 --g2 --n")
            result = two_stage(args.fcf0, args.r, args.g1, args.g2, args.n)
        else:
            if None in (args.g1, args.g2, args.g3, args.n, args.m):
                sys.exit("错误：三阶段模型需要 --g1 --g2 --g3 --n --m")
            result = three_stage(args.fcf0, args.r, args.g1, args.g2, args.g3, args.n, args.m)
    except ValueError as e:
        sys.exit(f"参数错误：{e}")

    result["unit"] = args.unit
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
