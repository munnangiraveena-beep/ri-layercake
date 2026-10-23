import katex from "katex";
import "katex/dist/katex.min.css";

export const metadata = { title: "Formulas · ri-layercake" };

// Rendered to HTML at build time; the page ships no maths JavaScript.
function TeX({ children, block = true }: { children: string; block?: boolean }) {
  const html = katex.renderToString(children, { displayMode: block, throwOnError: true, output: "html" });
  return block ? <div className="formula" dangerouslySetInnerHTML={{ __html: html }} /> : <span dangerouslySetInnerHTML={{ __html: html }} />;
}

/** One formula: what it means, the formula, a worked example with numbers, and where it appears. */
function Card({ id, title, meaning, tex, example, where, children }: {
  id: string; title: string; meaning: React.ReactNode; tex: string | string[]; example: React.ReactNode; where?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="fcard" id={id} aria-labelledby={`${id}-h`}>
      <h3 id={`${id}-h`}><a href={`#${id}`}>{title}</a></h3>
      <p className="fmeaning">{meaning}</p>
      {(Array.isArray(tex) ? tex : [tex]).map((t) => <TeX key={t}>{t}</TeX>)}
      <div className="fexample"><span className="flabel">Example</span>{example}</div>
      {children}
      {where && <p className="fwhere">In the app: {where}</p>}
    </section>
  );
}

const SECTIONS: [string, string][] = [
  ["layers", "Layers and shares"], ["pricing", "Pricing"], ["qs", "Quota share"], ["sl", "Stop loss"],
  ["terms", "Commercial terms"], ["walk", "Premium walk"], ["risk", "Optimising"],
];

export default function Formulas() {
  return (
    <article className="doc formulas">
      <h1>Formulas</h1>
      <p className="lead">
        Every number in ri-layercake comes from one of these formulas, each shown with what it means and a worked
        example. Amounts are in millions; limits and attachments are on a 100% basis, and shares are applied last.
      </p>
      <nav className="ftoc" aria-label="Sections">
        {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
      </nav>

      <h2 id="layers">Layers and shares</h2>
      <Card id="exhaust" title="Exhaust point" tex="E = A + L"
        meaning="The top of a layer: where its cover runs out. A layer “L xs A” starts paying above the attachment A and pays at most its limit L."
        example={<p>50 xs 50 attaches at 50 and exhausts at 50 + 50 = <b>100</b>.</p>}
        where="the Exhaust figure in the inspector and tooltip." />
      <Card id="trapped" title="Loss to a layer (trapped exposure)" tex="R = \operatorname{median}\big(0,\; X - A,\; L\big)"
        meaning="How much of a loss, or of a risk's exposure, falls inside a layer: nothing below the attachment, the excess above it, and never more than the limit. The median of the three numbers is the middle one, which does exactly that."
        example={<>
          <p>For the layer 40 xs 10:</p>
          <table><tbody>
            <tr><td>A 5 loss</td><td>median(0, −5, 40)</td><td><b>0</b> (below the attachment)</td></tr>
            <tr><td>A 30 loss</td><td>median(0, 20, 40)</td><td><b>20</b></td></tr>
            <tr><td>An 80 loss</td><td>median(0, 70, 40)</td><td><b>40</b> (exhausted)</td></tr>
          </tbody></table>
        </>}
        where="Exposure and loss coverage: Per risk and Portfolio." />
      <Card id="share" title="Order and placed shares" tex={["\\text{Share} = \\text{Order \\%} \\times \\text{Placed \\%}", "\\text{Recovery} = R \\times \\text{Share}"]}
        meaning="Order % is how much of the 100% layer the cedant puts to market (the rest it keeps as co-reinsurance). Placed % is how much of that order reinsurers actually signed. What is not placed stays with the cedant."
        example={<p>40 xs 10 with an 80% order, 90% placed: share = 80% × 90% = <b>72%</b>. A 30 loss puts 20 into the layer; reinsurers pay 20 × 72% = <b>14.4</b> and the cedant keeps <b>5.6</b>.</p>}
        where="the Order and Placed columns, and Share with reinsurers in the inspector; unplaced parts are drawn hatched." />

      <h2 id="pricing">Pricing</h2>
      <p>Price a layer with any one of premium, rate on line or adjusted rate; the other two follow. Entering one clears the others, so they never disagree.</p>
      <Card id="premium" title="Premium (RTE)" tex="\text{Premium (RTE)} = \text{EPI (gross)} \times \text{Adj. rate}"
        meaning="The reinsurance premium for the layer, on a 100% basis. The adjusted rate expresses it as a percentage of the cedant's gross estimated premium income (EPI)."
        example={<p>EPI 120 and an adjusted rate of 0.8%: premium = 120 × 0.8% = <b>0.96</b>.</p>}
        where="Premium (RTE) in the inspector, grid and table." />
      <Card id="rol" title="Rate on line and payback" tex={["\\text{ROL} = \\frac{\\text{Premium (RTE)}}{\\text{Layer limit}}", "\\text{Payback} = \\frac{\\text{Layer limit}}{\\text{Premium (RTE)}}"]}
        meaning="Rate on line is the premium as a share of the limit: what reinsurers charge per unit of cover. Payback is its inverse: how many loss-free years it takes the premium to pay for one total loss."
        example={<p>5 xs 5 at a premium of 0.96: ROL = 0.96 ÷ 5 = <b>19.2%</b>, payback = 5 ÷ 0.96 = <b>5.2 years</b>. Working layers often sit at 40–60% (payback around 2 years), top layers at 1–2%.</p>}
        where="ROL and Payback in the inspector; ROL in the table." />
      <Card id="adj" title="Adjusted rate" tex="\text{Adj. rate} = \frac{\text{ROL} \times \text{Layer limit}}{\text{EPI}}"
        meaning="The same price expressed on EPI instead of on the limit, which is how a layer's cost compares across the programme and against the cedant's income."
        example={<p>ROL 19.2% on a limit of 5 with EPI 120: 19.2% × 5 ÷ 120 = <b>0.8%</b>, back where we started.</p>}
        where="Adj. rate in the inspector and table." />
      <Card id="agg" title="Aggregate limit" tex="\text{Agg limit} = \text{Limit} \times (1 + \text{Reinstatements})"
        meaning="The most a layer can pay in a year: the original limit plus every reinstatement of it. Unlimited reinstatements mean no annual cap."
        example={<p>5 xs 5 with one reinstatement: 5 × (1 + 1) = <b>10</b> in the year. With two: 15.</p>}
        where="Agg limit in the inspector and table." />
      <Card id="rip" title="Reinstatement premium" tex="\text{RIP} = r \times \text{Premium} \times \frac{\min(R,\; n \times L)}{L}"
        meaning="Paid by the cedant to reinstate cover used by a loss, pro rata to the amount used: r is the reinstatement rate (100% = one full premium) and n the number of reinstatements."
        example={<p>5 xs 5 at 0.96 premium with 1 @ 100%. An 8 loss uses 3 of the 5: RIP = 100% × 0.96 × 3 ÷ 5 = <b>0.576</b>.</p>}
        where="Reinst. premium in coverage results and the premium walk." />

      <h2 id="qs">Quota share</h2>
      <Card id="qs-cession" title="Cession, limit and QS premium" tex={["\\text{QS ceded} = c \\times \\min(X,\\; L_{QS})", "\\text{QS premium} = c \\times \\text{EPI (gross)}"]}
        meaning="A quota share takes a fixed share c of every risk, up to its per-risk limit, which is usually the CRM team's limit for the largest counterparty. It takes the same share of the premium."
        example={<p>QS 20% with a limit of 50 and EPI 120: QS premium = 20% × 120 = <b>24</b>. A 30 risk cedes 20% × 30 = <b>6</b>; an 80 risk cedes 20% × 50 = <b>10</b> (capped by the limit) and the cedant keeps 70.</p>}
        where="QS premium in the inspector; the QS checks warn when the limit is above the counterparty limit." />
      <Card id="qs-stacked" title="Stacked: XoL on the net of the QS (default)" tex={["\\text{Net} = X - \\text{QS ceded}", "R_{XL} = \\operatorname{median}\\big(0,\\; \\text{Net} - A,\\; L\\big)"]}
        meaning="The QS cedes first; what is left passes through every excess of loss layer exactly as written."
        example={<p>Exposure 50, QS 20%: the QS takes 10 and the net 40 enters the XoL. A 40 xs 10 takes median(0, 40 − 10, 40) = <b>30</b>.</p>}
        where="the Stacked tick in the toolbar (on by default); the QS is drawn as a slab under the tower." />
      <Card id="qs-side" title="Side by side: XoL lowered by the cession" tex="R_{XL} = \operatorname{median}\big(0,\; \text{Net} - A(1-c),\; L(1-c)\big)"
        meaning="The XoL protects the retained share only, so each layer's attachment and limit are lowered by the QS cession while calculating."
        example={<p>Same exposure 50 and QS 20%: the 40 xs 10 works as 32 xs 8 on the net 40 and takes median(0, 40 − 8, 32) = <b>32</b>.</p>}
        where="untick Stacked; the QS is drawn as its own column beside the tower." />

      <Card id="qs-lines" title="Lines with their own QS cession" tex={["\\text{QS premium} = \\sum_i c_i \\times \\text{EPI}_i", "\\text{EL saved by QS} = \\sum_i c_i \\times \\text{EPI}_i \\times \\text{EL}_i"]}
        meaning="One QS treaty can cede a different share of each line in the programme; the XoL and stop loss sit over the combined net. Each risk is ceded at its own line's cession."
        example={<p>Credit EPI 200 at 20% and Surety EPI 60 at 30%: QS premium = 20% × 200 + 30% × 60 = <b>58</b>. With expected loss ratios of 50% and 45%, EL saved = 20% × 100 + 30% × 27 = <b>28.1</b>. A 20 credit risk cedes 4; the same risk in surety cedes 6.</p>}
        where="Lines in the Programme panel; Risk is in under Per risk coverage." />

      <h2 id="sl">Stop loss</h2>
      <Card id="sl" title="Stop loss on the net loss ratio" tex={["\\text{LR} = \\frac{X_{agg} - \\text{QS ceded}}{\\text{EPI}}", "R_{SL} = \\operatorname{median}(0,\\; \\text{LR} - a,\\; l) \\times \\text{EPI}"]}
        meaning="A stop loss protects the year's aggregate result. It is set as loss ratios of the gross EPI: “20% xs 85%” pays once the net loss ratio passes 85%, for up to 20 points."
        example={<p>EPI 80 with SL 20% xs 85%. A year with a net loss of 76 is a 95% loss ratio, so the stop loss pays 95% − 85% = 10 points = <b>8</b>.</p>}
        where="Exposure and loss coverage: Annual aggregate." />

      <h2 id="terms">Commercial terms</h2>
      <Card id="comm" title="QS commission" tex="\text{QS commission} = \text{Commission \%} \times \text{QS premium}"
        meaning="Reinsurers pay the cedant a commission on the ceded premium to cover its acquisition and running costs, so a QS commission usually sits close to the cedant's internal expense ratio."
        example={<p>A 32% commission on a QS premium of 24: <b>7.68</b>.</p>}
        where="QS terms in the inspector." />
      <Card id="ss" title="Sliding scale commission" tex="\text{Comm}(\text{LR}) = \text{max} - (\text{max} - \text{min}) \times \frac{\text{LR} - \text{LR}_{low}}{\text{LR}_{high} - \text{LR}_{low}}"
        meaning="Instead of a flat rate, the commission slides with the QS loss ratio: the maximum at or below a low loss ratio, the minimum at or above a high one, and a straight line between. Good years earn more commission."
        example={<p>40% at a loss ratio of 40% or less, 30% at 65% or more. At a 50% loss ratio: 40% − 10% × (50 − 40) ÷ (65 − 40) = <b>36%</b>.</p>}
        where="QS terms; Annual aggregate shows the rate for a given year." />
      <Card id="pc" title="Reinsurer management expenses and profit commission" tex={["\\text{RME} = \\text{RME \\%} \\times \\text{QS premium}", "\\text{Profit comm.} = \\text{PC \\%} \\times \\max\\big(0,\\; \\text{QS premium} - \\text{QS losses} - \\text{Commission} - \\text{RME}\\big)"]}
        meaning="Reinsurers keep an allowance for their own expenses, then share any profit left on the QS back with the cedant. A loss-making year pays no profit commission (losses are not carried forward in this version)."
        example={<p>QS premium 80, losses 40 (a 50% loss ratio, so a 36% sliding commission = 28.8), RME 5% = 4. Profit = 80 − 40 − 28.8 − 4 = 7.2, and a 20% profit commission pays <b>1.44</b>.</p>}
        where="QS terms and the Annual aggregate results." />
      <Card id="ncb" title="No claims bonus" tex="\text{NCB} = \text{NCB \%} \times \text{Premium (RTE)} \quad \text{if the layer has no claims in the year}"
        meaning="Part of an XoL layer's premium is returned if the layer stays claim-free for the year."
        example={<p>10% on a premium of 0.42: <b>0.042</b> back if 10 xs 10 has no claims. Per risk coverage marks NCB lost when a loss reaches the layer.</p>}
        where="XL terms in the inspector." />

      <h2 id="walk">Premium walk</h2>
      <Card id="walk-f" title="From EPI to result and margin"
        tex={["\\begin{aligned}\\text{Result} = {} & \\text{EPI} - \\text{Internal expenses} - \\text{QS premium} - \\text{XL premium} - \\text{Reinst. premium} - \\text{EL (analytic)} \\\\ & + \\text{EL saved by QS} + \\text{EL saved by XL} + \\text{QS commission} + \\text{Profit comm.} + \\text{NCB} \\\\ & - \\text{Brokerage} - \\text{Tax}\\end{aligned}", "\\text{Margin} = \\frac{\\text{Result}}{\\text{EPI}}"]}
        meaning="What the cedant keeps after expenses, expected losses and the net cost of its reinsurance. Comparing the result with and without reinsurance gives the cost of the programme."
        example={<>
          <p>The per risk XoL starter tower: EPI 120, analytic EL 55%, layers priced at 0.96–1.8 with their expected losses.</p>
          <table><tbody>
            <tr><td>EPI (gross)</td><td>120</td></tr>
            <tr><td>− Internal expenses (30% default)</td><td>36</td></tr>
            <tr><td>− XL premium</td><td>3.4</td></tr>
            <tr><td>− Reinst. premium *</td><td>0.8</td></tr>
            <tr><td>− EL (analytic) 55%</td><td>66</td></tr>
            <tr><td>+ EL saved by XL *</td><td>1.7</td></tr>
            <tr><td>− Brokerage (10% of XL premium)</td><td>0.3</td></tr>
            <tr><td><b>Result</b></td><td><b>15.3</b></td></tr>
            <tr><td>Margin</td><td>12.8%</td></tr>
          </tbody></table>
          <p>Without reinsurance the result would be 18, so the programme costs 2.7 a year in expected terms.</p>
        </>}
        where="the Premium walk panel, with This portfolio and All portfolios.">
        <ul className="fnotes">
          <li><b>Defaults</b> when not entered: internal expenses 30% of EPI; brokerage 10% of XL and stop loss premium and 2.5% of QS premium.</li>
          <li><b>Approximations</b> (marked *): EL saved by QS ≈ cession × EL (analytic), capped by the QS aggregate limit; EL saved by XL is each layer&apos;s expected loss you enter; reinstatement premium ≈ r × premium × min(layer EL, n × limit) ÷ limit; QS commission and profit commission use the expected ceded loss ratio; NCB is counted in full, assuming no claims.</li>
          <li><b>Tax</b> is a rate on ceded reinsurance premium.</li>
          <li>Reinsurance figures are at each cover&apos;s share (order × placed).</li>
        </ul>
      </Card>

      <Card id="before-after" title="Before and after reinsurance"
        tex={["\\text{Net premium} = \\text{EPI} - \\text{QS premium} - \\text{XL premium} - \\text{Reinst. premium}",
              "\\text{Net loss ratio} = \\frac{\\text{EL} - \\text{EL saved by QS} - \\text{EL saved by XL}}{\\text{Net premium}}",
              "\\text{Margin} = \\frac{\\text{Result}}{\\text{Gross EPI}} \\quad \\text{(the same base before and after)}"]}
        meaning="The same programme seen gross and net: loss ratio, expense ratio, combined ratio and margin. Margin is on gross EPI in both columns so the drop is the expected cost of reinsurance; margin on each column's own premium is shown too."
        example={<p>Credit and surety programme: margin 21.2% before reinsurance and 17.0% after, so the programme costs about 4.2 points of EPI in an average year. What it buys shows in the bad year, below.</p>}
        where="the Before RI / After RI table under the Premium walk." />

      <h2 id="risk">Optimising: loss ratio, margin, capital and RoC</h2>
      <Card id="optimise" title="Return on capital and the efficient frontier"
        tex={["\\text{Net LR} = \\frac{\\text{Gross losses} - \\text{Recoveries}}{\\text{Gross EPI}}, \\qquad \\text{Margin} = \\frac{\\text{Result}}{\\text{Gross EPI}}",
              "\\text{Capital} = \\text{Expected result} - \\text{Result in a 1-in-}N\\text{ year}",
              "\\text{RoC} = \\frac{\\text{Expected result}}{\\text{Capital}}"]}
        meaning="Everything is on gross EPI. Reinsurance lowers the net loss ratio and the capital a bad year needs; because reinsurers keep a margin, it also costs some expected margin. Return on capital says whether that trade is worth it. The optimiser simulates 20,000 years of the whole programme and maps RoC across two levers (QS cession by line, QS commission, XoL retention, XoL price, stop loss attachment). The efficient frontier plots every programme by capital and expected margin: points up and to the left are better, rays through the origin are lines of equal RoC, and the best balance of the three is starred, and a third chart shows net loss ratio, margin and RoC side by side for every efficient programme."
        example={<p>Credit and surety, 1-in-200 year: with no reinsurance, net LR 48.9%, margin 21.1%, bad year −21.2%, capital 110, RoC 50.0%. With the 35% / 15% QS and XoL: net LR 33.4%, margin 16.4%, bad year −14.0%, capital 79, <b>RoC 53.9%</b>. The map finds 50% credit and no surety QS at <b>RoC 56.7%</b>: ceding credit pays for the capital it frees; ceding surety does not.</p>}
        where="Optimise reinsurance, under the canvas.">
        <ul className="fnotes">
          <li><b>Losses</b>: attritional losses are lognormal around (1 − large share) × EL with the line&apos;s volatility, correlated between lines. Large losses are a Poisson number a year with Pareto sizes, calibrated so the modelled XoL layer losses match the layer ELs you enter.</li>
          <li><b>Programme</b>: each large loss goes through the QS at its line&apos;s cession up to the QS limit, then the XoL (stacked or side by side), with the annual cap, reinstatement premium and NCB; the stop loss pays on the year&apos;s net loss ratio.</li>
          <li><b>Re-pricing</b>: when cession or retention change, XoL premiums follow the modelled layer exposure at the layer&apos;s current loading, times the price lever.</li>
          <li><b>Placeable</b>: QS cession at most the market maximum (50% by default); reinsurers keep at least 3% after losses, commission, expenses and brokerage, on the QS and on every layer; no layer above 100% rate on line; a stop loss attaches at least 5 points above the expected net loss ratio.</li>
          <li><b>The best balance</b>: of the placeable programmes on the map, only the efficient ones count (none is at least as good on net loss ratio, margin and RoC and better on one). Each measure is scaled from 0 (worst on the map) to 1 (best), and the best programme has the highest weighted sum: equal weights by default, adjustable under What matters. All weight on RoC gives the highest return on capital.</li>
        </ul>
      </Card>

      <p className="muted">Outputs are illustrative, based on the inputs provided, and not pricing or actuarial advice.</p>
    </article>
  );
}
