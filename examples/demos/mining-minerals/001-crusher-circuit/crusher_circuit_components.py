"""Crusher circuit components for the Plugboard PBM comminution demo.

Implements a closed-circuit crushing plant with:
- FeedSource: generates ore with an initial PSD
- Crusher: Whiten/King PBM model for size reduction
- Screen: Whiten efficiency curve for classification
- Conveyor: transport delay for the recirculation loop
- ProductCollector: tracks product quality metrics

References:
    Whiten, W.J. (1974). A matrix theory of comminution machines.
        Chemical Engineering Science, 29(2), 589-599.
    King, R.P. (2001). Modeling and Simulation of Mineral Processing Systems.
        Butterworth-Heinemann.
    Austin, L.G. & Luckie, P.T. (1972). Methods for determination of breakage
        distribution parameters. Powder Technology, 5(4), 215-222.
"""

import typing as _t

from pydantic import BaseModel, field_validator

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class PSD(BaseModel):
    """Particle Size Distribution.

    Tracks the mass fraction retained in each discrete size class,
    together with the absolute mass flow (tonnes) of the stream.

    Size classes are defined by their upper boundary (in mm),
    ordered from coarsest to finest.
    """

    size_classes: list[float]
    mass_fractions: list[float]
    mass_tonnes: float = 1.0

    @field_validator("mass_fractions")
    @classmethod
    def validate_fractions(cls, v: list[float]) -> list[float]:
        """Normalise mass fractions so they sum to 1."""
        total = sum(v)
        if abs(total - 1.0) > 1e-6 and total > 0:
            return [f / total for f in v]
        return v

    def _percentile_size(self, target: float) -> float:
        """Interpolated percentile passing size (mm)."""
        cumulative = 0.0
        for i in range(len(self.size_classes) - 1, -1, -1):
            prev_cum = cumulative
            cumulative += self.mass_fractions[i]
            if cumulative >= target:
                if self.mass_fractions[i] > 0:
                    frac = (target - prev_cum) / self.mass_fractions[i]
                else:
                    frac = 0.0
                lower = self.size_classes[i + 1] if i < len(self.size_classes) - 1 else 0.0
                return lower + frac * (self.size_classes[i] - lower)
        return self.size_classes[0]

    @property
    def d80(self) -> float:
        """80th percentile passing size (mm), interpolated."""
        return self._percentile_size(0.80)

    @property
    def d50(self) -> float:
        """50th percentile passing size (mm), interpolated."""
        return self._percentile_size(0.50)

    def to_cumulative_passing(self) -> list[float]:
        """Return cumulative % passing for each size class."""
        result: list[float] = []
        cumulative = 0.0
        for i in range(len(self.size_classes) - 1, -1, -1):
            cumulative += self.mass_fractions[i]
            result.insert(0, cumulative * 100)
        return result


# ---------------------------------------------------------------------------
# PBM helper functions
# ---------------------------------------------------------------------------


def build_selection_vector(
    size_classes: list[float],
    css: float,
    oss: float,
    k3: float = 2.3,
) -> list[float]:
    """Build the crusher selection (classification) vector.

    Implements the Whiten classification function:
    - Particles smaller than CSS pass through unbroken (S=0)
    - Particles larger than OSS are always broken (S=1)
    - Particles between CSS and OSS have a fractional probability

    Args:
        size_classes: Upper bounds of each size class (mm), coarsest first.
        css: Closed-side setting (mm).
        oss: Open-side setting (mm).
        k3: Shape parameter controlling the classification curve steepness.

    Returns:
        Selection probability for each size class.
    """
    selection: list[float] = []
    for d in size_classes:
        if d <= css:
            selection.append(0.0)
        elif d >= oss:
            selection.append(1.0)
        else:
            x = (d - css) / (oss - css)
            selection.append(1.0 - (1.0 - x) ** k3)
    return selection


def build_breakage_matrix(
    size_classes: list[float],
    phi: float = 0.4,
    gamma: float = 1.5,
    beta: float = 3.5,
) -> list[list[float]]:
    """Build the breakage distribution matrix (Austin & Luckie, 1972).

    B[i][j] is the fraction of material broken from size class j
    that reports to size class i.

    The cumulative breakage function is:
        B_cum(i,j) = phi * (x_i/x_j)^gamma + (1 - phi) * (x_i/x_j)^beta

    Args:
        size_classes: Upper bounds of each size class (mm), coarsest first.
        phi: Fraction of breakage due to impact (vs. abrasion).
        gamma: Exponent for impact breakage.
        beta: Exponent for abrasion breakage.

    Returns:
        Lower-triangular breakage matrix B[i][j].
    """
    n = len(size_classes)
    b_cum = [[0.0] * n for _ in range(n)]

    for j in range(n):
        for i in range(j, n):
            if i == j:
                b_cum[i][j] = 1.0
            else:
                ratio = size_classes[i] / size_classes[j]
                b_cum[i][j] = phi * ratio**gamma + (1.0 - phi) * ratio**beta

    # Convert cumulative to fractional (incremental) breakage
    b_mat: list[list[float]] = [[0.0] * n for _ in range(n)]
    for j in range(n):
        for i in range(j + 1, n):
            if i == n - 1:
                b_mat[i][j] = b_cum[i][j]
            else:
                b_mat[i][j] = b_cum[i][j] - b_cum[i + 1][j]

    return b_mat


def apply_crusher(feed: PSD, selection: list[float], b_mat: list[list[float]]) -> PSD:
    """Apply one pass of the Whiten crusher model.

    P = [B·S + (I - S)] · F

    Args:
        feed: Input particle size distribution.
        selection: Selection vector (diagonal of S matrix).
        b_mat: Breakage matrix.

    Returns:
        Product particle size distribution (mass_tonnes preserved).
    """
    n = len(feed.size_classes)
    f = feed.mass_fractions
    product = [0.0] * n

    for i in range(n):
        product[i] += (1.0 - selection[i]) * f[i]
        for j in range(i):
            product[i] += b_mat[i][j] * selection[j] * f[j]

    total = sum(product)
    if total > 0:
        product = [p / total for p in product]

    return PSD(
        size_classes=feed.size_classes,
        mass_fractions=product,
        mass_tonnes=feed.mass_tonnes,
    )


def screen_partition(
    size_classes: list[float],
    d50c: float,
    alpha: float = 4.0,
    bypass: float = 0.05,
) -> list[float]:
    """Calculate screen partition (efficiency) curve.

    Uses a logistic partition model for the screen. Returns the
    fraction of material in each size class that reports to the
    undersize (product) stream.

    The partition to undersize is:
        E_undersize(d) = (1 - bypass) / (1 + (d / d50c)^alpha)

    This gives 50% efficiency at the cut-point size d50c, with
    the sharpness parameter alpha controlling the steepness of
    the transition.

    Args:
        size_classes: Upper bounds of each size class (mm), coarsest first.
        d50c: Corrected cut-point size (mm) — 50% partition size.
        alpha: Sharpness of separation (higher = sharper cut).
        bypass: Fraction of fines that misreport to oversize.

    Returns:
        Efficiency (fraction passing to undersize) for each size class.

    References:
        King, R.P. (2001). Modeling and Simulation of Mineral Processing
        Systems, Ch. 8. Butterworth-Heinemann.
    """
    efficiency: list[float] = []
    for d in size_classes:
        e_undersize = (1.0 - bypass) / (1.0 + (d / d50c) ** alpha)
        efficiency.append(e_undersize)
    return efficiency


# ---------------------------------------------------------------------------
# Plugboard components
# ---------------------------------------------------------------------------


class FeedSource(Component):
    """Generates a feed stream with a fixed particle size distribution."""

    io = IO(outputs=["feed_psd"])

    def __init__(
        self,
        size_classes: list[float],
        feed_fractions: list[float],
        feed_tonnes: float = 100.0,
        total_steps: int = 50,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._psd = PSD(
            size_classes=size_classes,
            mass_fractions=feed_fractions,
            mass_tonnes=feed_tonnes,
        )
        self._total_steps = total_steps
        self._step_count = 0

    async def step(self) -> None:
        """Emit the feed PSD until the configured number of steps is reached."""
        if self._step_count < self._total_steps:
            self.feed_psd = self._psd.model_dump()
            self._step_count += 1
        else:
            await self.io.close()


class Crusher(Component):
    """Whiten/King crusher model.

    Receives a feed PSD (fresh feed combined with recirculated oversize)
    and applies the PBM to produce a crushed product PSD.  Mass-weighted
    mixing ensures the feed-to-recirculation ratio evolves dynamically.
    """

    io = IO(inputs=["feed_psd", "recirc_psd"], outputs=["product_psd"])

    def __init__(
        self,
        css: float = 12.0,
        oss: float = 25.0,
        k3: float = 2.3,
        phi: float = 0.4,
        gamma: float = 1.5,
        beta: float = 3.5,
        n_stages: int = 3,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._css = css
        self._oss = oss
        self._k3 = k3
        self._phi = phi
        self._gamma = gamma
        self._beta = beta
        self._n_stages = n_stages
        self._selection: list[float] | None = None
        self._breakage: list[list[float]] | None = None

    async def step(self) -> None:
        """Combine fresh feed with recirculated oversize and crush."""
        feed = PSD(**self.feed_psd)

        if self._selection is None:
            self._selection = build_selection_vector(
                feed.size_classes, self._css, self._oss, self._k3
            )
            self._breakage = build_breakage_matrix(
                feed.size_classes, self._phi, self._gamma, self._beta
            )

        # Mass-weighted mixing of fresh feed and recirculated oversize
        recirc = self.recirc_psd
        if recirc is not None:
            recirc_psd = PSD(**recirc)
            feed_mass = feed.mass_tonnes
            recirc_mass = recirc_psd.mass_tonnes
            total_mass = feed_mass + recirc_mass
            w_f = feed_mass / total_mass
            w_r = recirc_mass / total_mass
            combined = [
                w_f * f + w_r * r for f, r in zip(feed.mass_fractions, recirc_psd.mass_fractions)
            ]
            feed = PSD(
                size_classes=feed.size_classes,
                mass_fractions=combined,
                mass_tonnes=total_mass,
            )

        result = feed
        if self._breakage is None:
            msg = "Breakage matrix not initialised"
            raise RuntimeError(msg)
        for _ in range(self._n_stages):
            result = apply_crusher(result, self._selection, self._breakage)

        self.product_psd = result.model_dump()


class Screen(Component):
    """Vibrating screen separator using the Whiten efficiency model.

    Splits mass between undersize and oversize streams based on the
    partition curve.  Each output stream carries its share of the
    total mass flow.
    """

    io = IO(inputs=["crusher_product"], outputs=["undersize", "oversize"])

    def __init__(
        self,
        d50c: float = 15.0,
        alpha: float = 4.0,
        bypass: float = 0.05,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._d50c = d50c
        self._alpha = alpha
        self._bypass = bypass

    async def step(self) -> None:
        """Split crusher product into undersize and oversize streams."""
        feed = PSD(**self.crusher_product)
        efficiency = screen_partition(feed.size_classes, self._d50c, self._alpha, self._bypass)

        undersize_fracs: list[float] = []
        oversize_fracs: list[float] = []
        for i, f in enumerate(feed.mass_fractions):
            undersize_fracs.append(f * efficiency[i])
            oversize_fracs.append(f * (1.0 - efficiency[i]))

        u_total = sum(undersize_fracs)
        o_total = sum(oversize_fracs)

        # Mass split: proportion reporting to each stream
        undersize_mass = feed.mass_tonnes * u_total
        oversize_mass = feed.mass_tonnes * o_total

        if u_total > 0:
            undersize_fracs = [u / u_total for u in undersize_fracs]
        if o_total > 0:
            oversize_fracs = [o / o_total for o in oversize_fracs]

        self.undersize = PSD(
            size_classes=feed.size_classes,
            mass_fractions=undersize_fracs,
            mass_tonnes=undersize_mass,
        ).model_dump()
        self.oversize = PSD(
            size_classes=feed.size_classes,
            mass_fractions=oversize_fracs,
            mass_tonnes=oversize_mass,
        ).model_dump()


class Conveyor(Component):
    """Transport delay for the recirculation loop.

    Simulates a conveyor belt by buffering PSDs in a FIFO queue.
    The output is delayed by ``delay_steps`` time steps, creating
    realistic transient dynamics in the circuit.
    """

    io = IO(inputs=["input_psd"], outputs=["output_psd"])

    def __init__(
        self,
        delay_steps: int = 3,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._delay_steps = delay_steps
        self._buffer: list[dict[str, _t.Any] | None] = [None] * delay_steps

    async def step(self) -> None:
        """Push new material onto the buffer, pop the oldest."""
        self._buffer.append(self.input_psd)
        delayed = self._buffer.pop(0)
        self.output_psd = delayed


class ProductCollector(Component):
    """Collects the final product stream and tracks quality metrics."""

    io = IO(inputs=["product_psd"], outputs=["d80", "d50"])

    def __init__(
        self,
        target_d80: float = 20.0,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._target_d80 = target_d80
        self.psd_history: list[dict[str, _t.Any]] = []

    async def step(self) -> None:
        """Record the product PSD and emit quality metrics."""
        psd = PSD(**self.product_psd)
        self.psd_history.append(psd.model_dump())
        self.d80 = psd.d80
        self.d50 = psd.d50
