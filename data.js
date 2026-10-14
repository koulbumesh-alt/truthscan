/* =====================================================================
   TRUTHSCAN AI — MOCK DATA (PROTOTYPE / DEMO DATA)
   No real API, database, or ML model. All results are simulated.
   ===================================================================== */

/* Muted, editorial "duotone" palette — sophisticated newsroom tones
   rather than neon tech gradients. */
const CATEGORY_THEME = {
  India:         { a: '#5b2e1f', b: '#b56b35', icon: '🇮🇳' },
  Technology:    { a: '#2b3a55', b: '#516b8c', icon: '🖥️' },
  World:         { a: '#243b53', b: '#4a6b8a', icon: '🌍' },
  Science:       { a: '#264653', b: '#3d7a86', icon: '🔬' },
  Business:      { a: '#3a2f2a', b: '#8a6d4f', icon: '📈' },
  Sports:        { a: '#25402f', b: '#4e7a53', icon: '🏟️' },
  Entertainment: { a: '#3b2a3f', b: '#7a5670', icon: '🎬' },
  Space:         { a: '#1f2a44', b: '#3f4e78', icon: '🛰️' },
  Climate:       { a: '#24382e', b: '#4c7a63', icon: '🌦️' },
};

/* Build a restrained SVG "photograph" placeholder as a data URI so the
   prototype is fully self-contained (works offline / in sandboxed
   previews) yet reads like an editorial news photo, not a tech splash. */
function makeImage(category, seed = 1) {
  const t = CATEGORY_THEME[category] || CATEGORY_THEME.Technology;
  let s = seed * 9301 + 49297;
  const rnd = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  // soft overlapping "depth" shapes for a photographic feel
  const shapes = [];
  for (let i = 0; i < 4; i++) {
    const cx = (rnd()*800)|0, cy = (rnd()*450)|0, r = (rnd()*260+140)|0;
    shapes.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="black" opacity="${(rnd()*0.14+0.04).toFixed(2)}"/>`);
    shapes.push(`<circle cx="${800-cx}" cy="${(rnd()*450)|0}" r="${(r*0.7)|0}" fill="white" opacity="${(rnd()*0.08+0.03).toFixed(2)}"/>`);
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="0.8" y2="1">
        <stop offset="0" stop-color="${t.b}"/><stop offset="1" stop-color="${t.a}"/>
      </linearGradient>
      <linearGradient id="v" x1="0" y1="1" x2="0" y2="0">
        <stop offset="0" stop-color="black" stop-opacity="0.45"/>
        <stop offset="0.6" stop-color="black" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect width="800" height="450" fill="url(#g)"/>
    ${shapes.join('')}
    <rect width="800" height="450" fill="url(#v)"/>
    <text x="400" y="232" font-family="Georgia, serif" font-size="120" text-anchor="middle" opacity="0.28">${t.icon}</text>
    <text x="36" y="412" font-family="Helvetica, Arial" font-size="20" letter-spacing="3" font-weight="bold" fill="white" opacity="0.85">${category.toUpperCase()}</text>
    <text x="764" y="412" font-family="Helvetica, Arial" font-size="12" letter-spacing="2" text-anchor="end" fill="white" opacity="0.6">TRUTHSCAN · DEMO IMAGE</text>
  </svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

/* =====================================================================
   ARTICLES — each has a fully pre-baked simulated AI analysis.
   ===================================================================== */
const ARTICLES = [
  {
    id: 'a1',
    category: 'Technology',
    headline: 'New AI Technology Could Transform Education Worldwide',
    description: 'Researchers unveil an adaptive learning system that personalizes lessons in real time, sparking debate among educators.',
    source: 'Example News Network',
    author: 'John Example',
    time: '2 hours ago',
    date: 'Sep 30, 2026',
    trending: true,
    topics: ['#AI', '#Technology', '#Education'],
    keywords: ['ai', 'technology', 'education', 'learning', 'teacher', 'student', 'system'],
    body: [
      'A team of researchers has unveiled what they describe as a breakthrough adaptive learning platform that uses artificial intelligence to tailor lessons to each individual student in real time. The system, currently in a limited pilot, reportedly adjusts difficulty, pacing, and examples based on a learner\'s responses.',
      'Supporters say the approach could help close achievement gaps by giving every student a personalized tutor. Early pilot data from a handful of classrooms suggests improved engagement, though the sample sizes remain small and results have not yet been peer reviewed.',
      'Some observers have made far bolder claims, suggesting the technology is already being used worldwide and could completely replace teachers within a few years. Education experts caution that such statements outpace the available evidence and that human instruction remains central to learning.',
      'The developers acknowledge open questions around data privacy, algorithmic bias, and long-term learning outcomes. Independent studies will be needed before any broad conclusions can be drawn.'
    ],
    analysis: {
      score: 72,
      verdict: 'LIKELY CREDIBLE',
      confidence: 'MEDIUM',
      summary: 'The article contains several factual claims. Some have supporting information, while others require additional verification. The article also uses emotionally charged language in places, which slightly lowers the credibility score.',
      claims: [
        { text: 'Scientists developed a new AI system that personalizes lessons in real time.', status: 'support', note: 'Supporting information found. Consistent with named research pilots and public statements from the development team.' },
        { text: 'The technology is already being used worldwide.', status: 'warn', note: 'Needs verification. The article references a limited pilot, not global deployment. This broader claim is unsupported.' },
        { text: 'It will completely replace teachers.', status: 'warn', note: 'Potentially exaggerated. This is presented as speculation and contradicted by education experts quoted in the same article.' },
      ],
      language: [
        { label: 'Sensational Language', value: 62 },
        { label: 'Clickbait Indicators', value: 48 },
        { label: 'Emotional Language', value: 55 },
        { label: 'Exaggerated Claims', value: 58 },
      ],
      langNote: 'The article mixes measured reporting with a few sensational phrases ("transform," "completely replace"). The strongest claims are attributed to unnamed observers rather than the researchers themselves.',
      sourceAnalysis: {
        source: 'Example News Network', author: 'John Example', published: '2 hours ago',
        transparency: 'ok', citations: 'warn', original: 'unknown'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'Adaptive AI tutor personalizes lessons.' },
        { stage: 'EVIDENCE', status: 'warn', text: 'Small pilot data, not yet peer reviewed.' },
        { stage: 'SOURCE', status: 'support', text: 'Named research team, on-record statements.' },
        { stage: 'COMPARISON', status: 'warn', text: 'Broader "worldwide use" claim not corroborated.' },
        { stage: 'AI ASSESSMENT', status: 'support', text: 'Core story plausible; some claims overstated.' },
      ],
      verify: ['Original source', 'Publication date', 'Author', 'Supporting evidence', 'Independent reports'],
    },
  },
  {
    id: 'a2',
    category: 'Space',
    headline: 'Astronomers Detect Unusual Signals From a Distant Star System',
    description: 'A new telescope survey captures repeating radio bursts, prompting careful analysis and cautious optimism among scientists.',
    source: 'Orbital Science Daily',
    author: 'Dr. Aria Vance',
    time: '5 hours ago',
    date: 'Sep 30, 2026',
    trending: true,
    topics: ['#Space', '#Science', '#Astronomy'],
    keywords: ['space', 'star', 'signal', 'astronomy', 'telescope', 'radio', 'science', 'discovery', 'galaxy'],
    body: [
      'Astronomers using a next-generation radio telescope array report the detection of a series of repeating fast radio bursts originating from a distant star system. The signals, catalogued over several weeks, show a regularity that has intrigued the research community.',
      'The team emphasizes that fast radio bursts are a known astrophysical phenomenon and that natural explanations — such as highly magnetized neutron stars — remain the leading hypotheses. The data has been submitted for peer review.',
      'Multiple independent observatories are being asked to confirm the detection. Researchers stress the importance of replication before drawing conclusions, and note that extraordinary claims require extraordinary evidence.'
    ],
    analysis: {
      score: 86,
      verdict: 'LIKELY CREDIBLE',
      confidence: 'HIGH',
      summary: 'The article reports a specific, verifiable observation and appropriately frames uncertainty. Claims are attributed to named researchers and the data is described as submitted for peer review, which raises the credibility score.',
      claims: [
        { text: 'Repeating radio bursts were detected from a distant star system.', status: 'support', note: 'Supporting information found. Consistent with a catalogued observation and named observatory.' },
        { text: 'Natural sources remain the leading explanation.', status: 'support', note: 'Supported by the scientific consensus on fast radio bursts.' },
        { text: 'Independent observatories are being asked to confirm.', status: 'unclear', note: 'Plausible and standard practice, but confirmation is pending at time of writing.' },
      ],
      language: [
        { label: 'Sensational Language', value: 24 },
        { label: 'Clickbait Indicators', value: 18 },
        { label: 'Emotional Language', value: 21 },
        { label: 'Exaggerated Claims', value: 15 },
      ],
      langNote: 'Language is measured and scientific. The article avoids over-claiming and explicitly frames uncertainty, which is a strong credibility signal.',
      sourceAnalysis: {
        source: 'Orbital Science Daily', author: 'Dr. Aria Vance', published: '5 hours ago',
        transparency: 'ok', citations: 'ok', original: 'ok'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'Repeating radio bursts detected.' },
        { stage: 'EVIDENCE', status: 'support', text: 'Catalogued over weeks; data submitted for review.' },
        { stage: 'SOURCE', status: 'support', text: 'Named telescope array and lead researcher.' },
        { stage: 'COMPARISON', status: 'unclear', text: 'Independent confirmation still pending.' },
        { stage: 'AI ASSESSMENT', status: 'support', text: 'Well-sourced, appropriately cautious report.' },
      ],
      verify: ['Original source', 'Peer-review status', 'Independent confirmation', 'Author credentials'],
    },
  },
  {
    id: 'a3',
    category: 'World',
    headline: 'Viral Social Media Claim About Global Water Ban Spreads Rapidly',
    description: 'A widely shared post alleges an imminent worldwide restriction on bottled water. Officials say no such policy exists.',
    source: 'TrendWire',
    author: 'Anonymous Contributor',
    time: '1 hour ago',
    date: 'Sep 30, 2026',
    trending: true,
    topics: ['#WorldNews', '#Misinformation'],
    keywords: ['world', 'water', 'ban', 'viral', 'social', 'claim', 'policy', 'global'],
    body: [
      'A post circulating across social platforms claims that governments will impose a sweeping worldwide ban on bottled water starting next month. The message has been shared hundreds of thousands of times, often accompanied by urgent, alarming captions.',
      'No official body has announced such a policy. The post cites an unnamed "leaked document" that could not be located or verified, and links lead to pages that have since been removed.',
      'Fact-checking organizations note the claim recycles language from previous hoaxes. Experts urge readers to check original government sources before sharing.'
    ],
    analysis: {
      score: 34,
      verdict: 'NEEDS VERIFICATION',
      confidence: 'MEDIUM',
      summary: 'The article describes a viral claim that lacks a verifiable original source. The underlying claim relies on an unnamed leaked document, uses urgent emotional language, and could not be corroborated by any official body.',
      claims: [
        { text: 'A worldwide ban on bottled water will begin next month.', status: 'contradict', note: 'No official announcement exists. Contradicted by the absence of any verifiable policy or government source.' },
        { text: 'A leaked document proves the policy.', status: 'warn', note: 'Needs verification. The referenced document is unnamed and could not be located.' },
        { text: 'The post has been shared widely.', status: 'support', note: 'Plausible and consistent with observed sharing metrics — but virality is not evidence of accuracy.' },
      ],
      language: [
        { label: 'Sensational Language', value: 88 },
        { label: 'Clickbait Indicators', value: 82 },
        { label: 'Emotional Language', value: 79 },
        { label: 'Exaggerated Claims', value: 74 },
      ],
      langNote: 'The claim relies heavily on urgency and alarm ("imminent," "act now"), a common pattern in misleading content. Sourcing is anonymous and unverifiable.',
      sourceAnalysis: {
        source: 'TrendWire', author: 'Anonymous Contributor', published: '1 hour ago',
        transparency: 'warn', citations: 'bad', original: 'unknown'
      },
      evidence: [
        { stage: 'CLAIM', status: 'contradict', text: 'Imminent global bottled-water ban.' },
        { stage: 'EVIDENCE', status: 'contradict', text: 'No verifiable document or policy exists.' },
        { stage: 'SOURCE', status: 'warn', text: 'Anonymous author; removed links.' },
        { stage: 'COMPARISON', status: 'warn', text: 'Recycles language from prior hoaxes.' },
        { stage: 'AI ASSESSMENT', status: 'warn', text: 'High risk of misinformation — verify before sharing.' },
      ],
      verify: ['Original source', 'Official government pages', 'Author identity', 'Independent fact-checks', 'Publication date'],
    },
  },
  {
    id: 'a4',
    category: 'Sports',
    headline: 'Underdog Club Stuns League Leaders in Late Comeback Thriller',
    description: 'A dramatic three-goal second half sees a rising team overturn the favorites in front of a record home crowd.',
    source: 'Global Sports Report',
    author: 'Marcus Lane',
    time: '3 hours ago',
    date: 'Sep 30, 2026',
    trending: true,
    topics: ['#Sports', '#Football'],
    keywords: ['sports', 'football', 'match', 'goal', 'team', 'league', 'club', 'game', 'player'],
    body: [
      'In one of the most dramatic matches of the season, an underdog club overturned a two-goal deficit to defeat the league leaders in a late comeback. The winning goal arrived deep into stoppage time before a record home crowd.',
      'Post-match statistics confirm the scoreline and the attendance figure, both published by the league. The manager praised the squad\'s resilience in a televised interview.',
      'Analysts note the result reshapes the title race, though several fixtures remain. Official standings have been updated to reflect the outcome.'
    ],
    analysis: {
      score: 90,
      verdict: 'LIKELY CREDIBLE',
      confidence: 'HIGH',
      summary: 'A straightforward sports report with verifiable, official statistics. The scoreline, attendance, and standings are corroborated by league data, and quotes are attributed to on-record interviews.',
      claims: [
        { text: 'The underdog club overturned a two-goal deficit to win.', status: 'support', note: 'Supported by official match report and published scoreline.' },
        { text: 'The match drew a record home crowd.', status: 'support', note: 'Attendance figure published by the league.' },
        { text: 'The result reshapes the title race.', status: 'unclear', note: 'Reasonable analysis, but a subjective projection rather than a hard fact.' },
      ],
      language: [
        { label: 'Sensational Language', value: 38 },
        { label: 'Clickbait Indicators', value: 22 },
        { label: 'Emotional Language', value: 44 },
        { label: 'Exaggerated Claims', value: 19 },
      ],
      langNote: 'Some dramatic framing ("stuns," "thriller") is typical of sports writing and does not undermine the factual core, which is well documented.',
      sourceAnalysis: {
        source: 'Global Sports Report', author: 'Marcus Lane', published: '3 hours ago',
        transparency: 'ok', citations: 'ok', original: 'ok'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'Late comeback victory.' },
        { stage: 'EVIDENCE', status: 'support', text: 'Official scoreline and attendance.' },
        { stage: 'SOURCE', status: 'support', text: 'Named reporter; televised quotes.' },
        { stage: 'COMPARISON', status: 'support', text: 'Matches league standings update.' },
        { stage: 'AI ASSESSMENT', status: 'support', text: 'Factually solid, well-attributed report.' },
      ],
      verify: ['Official league data', 'Match report', 'Publication date'],
    },
  },
  {
    id: 'a5',
    category: 'Business',
    headline: 'Startup Claims Its Chip Will Make All Competitors Obsolete Overnight',
    description: 'A funding-round press release promises revolutionary performance, but independent benchmarks are not yet available.',
    source: 'MarketPulse Wire',
    author: 'PR Desk',
    time: '6 hours ago',
    date: 'Sep 30, 2026',
    trending: false,
    topics: ['#Business', '#Technology'],
    keywords: ['business', 'startup', 'chip', 'funding', 'market', 'company', 'technology', 'investment'],
    body: [
      'A semiconductor startup announced a new processor it claims will "make all competitors obsolete overnight," timed alongside a major funding round. The press release cites internal tests showing dramatic performance gains.',
      'No independent benchmarks have been published, and the specific test conditions are not disclosed. Industry analysts note that internal figures often differ from real-world results.',
      'The company has not yet shipped the product. Several claims about market impact are framed as projections rather than demonstrated outcomes.'
    ],
    analysis: {
      score: 46,
      verdict: 'NEEDS VERIFICATION',
      confidence: 'MEDIUM',
      summary: 'This article is based largely on a company press release. The central performance claims rely on undisclosed internal testing, use promotional language, and lack independent verification, which lowers the credibility score.',
      claims: [
        { text: 'The chip will make all competitors obsolete overnight.', status: 'warn', note: 'Potentially exaggerated. Promotional framing with no independent evidence.' },
        { text: 'Internal tests show dramatic performance gains.', status: 'warn', note: 'Needs verification. Test conditions are undisclosed and not independently reproduced.' },
        { text: 'The company completed a major funding round.', status: 'support', note: 'Plausible and commonly verifiable through filings and investor statements.' },
      ],
      language: [
        { label: 'Sensational Language', value: 76 },
        { label: 'Clickbait Indicators', value: 64 },
        { label: 'Emotional Language', value: 51 },
        { label: 'Exaggerated Claims', value: 81 },
      ],
      langNote: 'Superlatives like "obsolete overnight" and "revolutionary" are hallmarks of marketing copy. The absence of independent benchmarks is a notable gap.',
      sourceAnalysis: {
        source: 'MarketPulse Wire', author: 'PR Desk', published: '6 hours ago',
        transparency: 'warn', citations: 'warn', original: 'unknown'
      },
      evidence: [
        { stage: 'CLAIM', status: 'warn', text: 'Revolutionary, market-ending performance.' },
        { stage: 'EVIDENCE', status: 'warn', text: 'Internal, undisclosed test conditions.' },
        { stage: 'SOURCE', status: 'warn', text: 'Press release / PR desk byline.' },
        { stage: 'COMPARISON', status: 'unclear', text: 'No independent benchmarks yet.' },
        { stage: 'AI ASSESSMENT', status: 'warn', text: 'Treat as promotional until verified.' },
      ],
      verify: ['Independent benchmarks', 'Funding filings', 'Original source', 'Author / PR disclosure'],
    },
  },
  {
    id: 'a6',
    category: 'Science',
    headline: 'Study Suggests Common Habit May Dramatically Extend Lifespan',
    description: 'A new paper links a daily routine to longevity, but experts warn correlation is not causation.',
    source: 'HealthField Journal',
    author: 'Dr. Nadia Roy',
    time: '8 hours ago',
    date: 'Sep 30, 2026',
    trending: true,
    topics: ['#Science', '#Health'],
    keywords: ['science', 'study', 'health', 'lifespan', 'research', 'habit', 'longevity', 'medical'],
    body: [
      'A newly published observational study reports an association between a common daily habit and longer lifespan among participants tracked over several years. The paper appears in a peer-reviewed journal.',
      'The authors are careful to note that the study shows correlation, not causation, and that unmeasured factors could explain the link. Some headlines about the study have overstated the findings.',
      'Independent scientists say the result is interesting but preliminary, and call for randomized trials before any health recommendations are made.'
    ],
    analysis: {
      score: 63,
      verdict: 'NEEDS VERIFICATION',
      confidence: 'MEDIUM',
      summary: 'The underlying study appears legitimate and peer reviewed, but popular framing overstates it. The core finding is correlational, and stronger causal claims in circulation require additional verification.',
      claims: [
        { text: 'A daily habit is associated with longer lifespan.', status: 'support', note: 'Supported by a peer-reviewed observational study.' },
        { text: 'The habit dramatically extends lifespan.', status: 'warn', note: 'Potentially exaggerated. The study shows correlation, not proven causation.' },
        { text: 'People should adopt the habit for longevity.', status: 'warn', note: 'Needs verification. Authors explicitly caution against recommendations pending trials.' },
      ],
      language: [
        { label: 'Sensational Language', value: 69 },
        { label: 'Clickbait Indicators', value: 58 },
        { label: 'Emotional Language', value: 47 },
        { label: 'Exaggerated Claims', value: 66 },
      ],
      langNote: 'The word "dramatically" and cause-implying phrasing exceed what an observational study can support. The source paper itself is more measured than the headline.',
      sourceAnalysis: {
        source: 'HealthField Journal', author: 'Dr. Nadia Roy', published: '8 hours ago',
        transparency: 'ok', citations: 'ok', original: 'warn'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'Habit correlated with longevity.' },
        { stage: 'EVIDENCE', status: 'warn', text: 'Observational; causation not established.' },
        { stage: 'SOURCE', status: 'support', text: 'Peer-reviewed journal, named author.' },
        { stage: 'COMPARISON', status: 'warn', text: 'Popular headlines overstate findings.' },
        { stage: 'AI ASSESSMENT', status: 'warn', text: 'Real study, exaggerated retelling.' },
      ],
      verify: ['Original paper', 'Study design (observational vs trial)', 'Independent reports', 'Author', 'Publication date'],
    },
  },
  {
    id: 'a7',
    category: 'Entertainment',
    headline: 'Beloved Franchise Announces Surprise Return After a Decade',
    description: 'Studio confirms a new installment with returning cast, ending years of fan speculation.',
    source: 'ScreenBeat',
    author: 'Priya Menon',
    time: '10 hours ago',
    date: 'Sep 30, 2026',
    trending: false,
    topics: ['#Entertainment', '#Film'],
    keywords: ['entertainment', 'film', 'movie', 'franchise', 'studio', 'cast', 'show', 'series'],
    body: [
      'A major studio has officially confirmed a new installment in a beloved franchise, more than a decade after the last release. The announcement, made at a public event, includes the return of several original cast members.',
      'Details such as the release window and plot remain limited, and the studio says more will be shared later. The confirmation itself is on the record and widely reported.',
      'Fan reaction has been enthusiastic. A few unofficial accounts have circulated unverified plot details that the studio has not confirmed.'
    ],
    analysis: {
      score: 78,
      verdict: 'LIKELY CREDIBLE',
      confidence: 'MEDIUM',
      summary: 'The core announcement is officially confirmed and widely reported, supporting credibility. Some surrounding plot details come from unofficial accounts and remain unverified.',
      claims: [
        { text: 'The studio confirmed a new installment.', status: 'support', note: 'Supported by an on-record announcement at a public event.' },
        { text: 'Original cast members are returning.', status: 'support', note: 'Confirmed as part of the official announcement.' },
        { text: 'Specific plot details have been revealed.', status: 'warn', note: 'Needs verification. Circulating plot claims come from unofficial accounts.' },
      ],
      language: [
        { label: 'Sensational Language', value: 41 },
        { label: 'Clickbait Indicators', value: 39 },
        { label: 'Emotional Language', value: 52 },
        { label: 'Exaggerated Claims', value: 30 },
      ],
      langNote: 'Enthusiastic tone is typical of entertainment coverage. The verified core (the announcement) is clearly separated from unverified fan speculation.',
      sourceAnalysis: {
        source: 'ScreenBeat', author: 'Priya Menon', published: '10 hours ago',
        transparency: 'ok', citations: 'warn', original: 'ok'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'New installment confirmed.' },
        { stage: 'EVIDENCE', status: 'support', text: 'Public event announcement.' },
        { stage: 'SOURCE', status: 'support', text: 'Named outlet and reporter.' },
        { stage: 'COMPARISON', status: 'warn', text: 'Plot leaks from unofficial accounts.' },
        { stage: 'AI ASSESSMENT', status: 'support', text: 'Announcement solid; details unconfirmed.' },
      ],
      verify: ['Official studio statement', 'Original source', 'Author', 'Independent reports'],
    },
  },
  {
    id: 'a8',
    category: 'Climate',
    headline: 'Coastal City Unveils Ambitious Plan to Cut Emissions by 2035',
    description: 'Local officials present a phased strategy backed by published targets and an independent oversight panel.',
    source: 'GreenLine News',
    author: 'Sam Okafor',
    time: '12 hours ago',
    date: 'Sep 30, 2026',
    trending: false,
    topics: ['#Climate', '#WorldNews'],
    keywords: ['climate', 'emissions', 'city', 'plan', 'environment', 'green', 'policy', 'carbon'],
    body: [
      'A coastal city has unveiled a detailed plan to substantially cut greenhouse-gas emissions by 2035, outlining phased targets across transport, buildings, and energy. The plan documents are published in full.',
      'An independent oversight panel will track progress and publish annual reports. Officials acknowledge that meeting the targets depends on funding and regional cooperation.',
      'Analysts describe the goals as ambitious but grounded, noting the plan includes measurable milestones rather than vague pledges.'
    ],
    analysis: {
      score: 81,
      verdict: 'LIKELY CREDIBLE',
      confidence: 'HIGH',
      summary: 'The plan is documented, includes measurable milestones, and will be tracked by an independent panel. Claims are specific and verifiable, though achieving the targets remains conditional on funding.',
      claims: [
        { text: 'The city published a phased emissions plan.', status: 'support', note: 'Supported by publicly available plan documents.' },
        { text: 'An independent panel will monitor progress.', status: 'support', note: 'Described with named oversight and annual reporting.' },
        { text: 'The targets will definitely be met by 2035.', status: 'unclear', note: 'Aspirational. Success is explicitly conditioned on funding and cooperation.' },
      ],
      language: [
        { label: 'Sensational Language', value: 28 },
        { label: 'Clickbait Indicators', value: 20 },
        { label: 'Emotional Language', value: 26 },
        { label: 'Exaggerated Claims', value: 23 },
      ],
      langNote: 'Language is measured and specific. The article distinguishes committed actions from conditional outcomes, a strong credibility signal.',
      sourceAnalysis: {
        source: 'GreenLine News', author: 'Sam Okafor', published: '12 hours ago',
        transparency: 'ok', citations: 'ok', original: 'ok'
      },
      evidence: [
        { stage: 'CLAIM', status: 'support', text: 'Phased 2035 emissions plan.' },
        { stage: 'EVIDENCE', status: 'support', text: 'Full plan documents published.' },
        { stage: 'SOURCE', status: 'support', text: 'Named officials and outlet.' },
        { stage: 'COMPARISON', status: 'support', text: 'Independent oversight and milestones.' },
        { stage: 'AI ASSESSMENT', status: 'support', text: 'Specific, documented, well-sourced.' },
      ],
      verify: ['Official plan documents', 'Oversight panel reports', 'Publication date', 'Independent analysis'],
    },
  },
];

// Attach generated images
ARTICLES.forEach((a, i) => { a.image = makeImage(a.category, i + 1); });

const TRENDING_TOPICS = ['#AI', '#Technology', '#Space', '#Science', '#WorldNews', '#Business', '#Sports', '#Climate'];

const CATEGORIES = ['All', 'India', 'Fact Check', 'Technology', 'Science', 'World', 'Business', 'Sports', 'Entertainment'];

// Seed history (demo)
const SEED_HISTORY = [
  { id: 'a1', date: 'Sep 30, 2026' },
  { id: 'a3', date: 'Sep 30, 2026' },
  { id: 'a2', date: 'Sep 29, 2026' },
];
