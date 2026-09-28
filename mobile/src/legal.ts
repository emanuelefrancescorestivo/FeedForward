/**
 * In-app legal text. Stores also require a public URL before submission;
 * hosting this copy is a deploy step, not something this repo can do by itself.
 * See docs/APP_STORE.md.
 */

export const PRIVACY = `FeedForward privacy policy

What we collect
- Account email and a hashed password.
- The demographic group and dietary filters you choose, so daily-need percentages and meal plans can use them.
- A session token stored on this device.

What we do not collect
- We do not read HealthKit or Google Fit in this version.
- We do not sell personal data.
- We do not store a medical record. Cautions are general information, not a chart of your conditions.

Why
The lawful basis is the contract of providing the account you asked for (GDPR Art. 6(1)(b)), and your consent for optional profile fields you can clear by deleting the account.

Retention and your rights
You can export your account data from Profile, and you can delete the account there. Deletion removes the user row. We do not keep a copy. To exercise access, export, or erasure another way, use the in-app controls; a hosted contact address must be added before store submission.

This text is the policy. It is not legal advice.`;

export const TERMS = `FeedForward terms

FeedForward is a nutritional information tool. It traces food → nutrient → goal using published reference values, a rule-based absorption model, and evidence grades.

It does not diagnose, treat, cure, or prevent any disease. It does not replace a dietitian, physician, or pharmacist. Words such as "supports" and "associated with" are not treatment claims.

Professional mode shows grades and citations for people who want the underlying references. Those citations are anchors, not a complete literature review, and must be checked before clinical use.

You are responsible for the accuracy of the demographic group and diet filters you enter. Infant formulas are not recommended by the goal explorer because this version has no infant demographic.

The service is provided as-is. Account deletion is available in Profile.`;
