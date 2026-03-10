"""Test the full circuit simulation with mass tracking + interpolated d80."""

import asyncio

from crusher_circuit import Conveyor, Crusher, FeedSource, PSD, ProductCollector, Screen
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

SIZE_CLASSES = [150.0, 106.0, 75.0, 53.0, 37.5, 26.5, 19.0, 13.2, 9.5, 6.7, 4.75]
FEED_FRACTIONS = [0.05, 0.10, 0.15, 0.20, 0.18, 0.12, 0.08, 0.05, 0.04, 0.02, 0.01]

connect = lambda src, tgt: AsyncioConnector(spec=ConnectorSpec(source=src, target=tgt))

process = LocalProcess(
    components=[
        FeedSource(
            name="feed",
            size_classes=SIZE_CLASSES,
            feed_fractions=FEED_FRACTIONS,
            feed_tonnes=100.0,
            total_steps=50,
        ),
        Crusher(
            name="crusher",
            css=12.0,
            oss=30.0,
            k3=2.3,
            n_stages=2,
            initial_values={"recirc_psd": [None]},
        ),
        Screen(name="screen", d50c=18.0, alpha=3.5, bypass=0.05),
        Conveyor(name="conveyor", delay_steps=3),
        ProductCollector(name="product", target_d80=20.0),
    ],
    connectors=[
        connect("feed.feed_psd", "crusher.feed_psd"),
        connect("crusher.product_psd", "screen.crusher_product"),
        connect("screen.undersize", "product.product_psd"),
        connect("screen.oversize", "conveyor.input_psd"),
        connect("conveyor.output_psd", "crusher.recirc_psd"),
    ],
)


async def main() -> None:
    async with process:
        await process.run()
    collector = process.components["product"]
    d80s = [PSD(**h).d80 for h in collector.psd_history]
    masses = [PSD(**h).mass_tonnes for h in collector.psd_history]
    print(f"Steps: {len(d80s)}")
    for i in [0, 1, 2, 3, 4, 5, 6, 7, 9, 14, 19, 29, 49]:
        if i < len(d80s):
            print(f"  Step {i + 1:>2}: d80={d80s[i]:.2f} mm, mass={masses[i]:.1f} t")
    unique_d80s = len(set(round(d, 4) for d in d80s))
    unique_masses = len(set(round(m, 4) for m in masses))
    print(f"\nUnique d80 values: {unique_d80s}")
    print(f"Unique mass values: {unique_masses}")
    print(f"d80 range: {min(d80s):.2f} - {max(d80s):.2f} mm")
    print(f"Mass range: {min(masses):.1f} - {max(masses):.1f} t")
    ok = unique_d80s > 1 and unique_masses > 1
    print("PASS" if ok else "FAIL - no dynamics")


asyncio.run(main())
