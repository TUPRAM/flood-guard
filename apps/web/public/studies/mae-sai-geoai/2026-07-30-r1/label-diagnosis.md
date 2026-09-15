# MNDWI label-quality diagnosis

Component B's training label, selectable and provenance-bound.

Why this module exists
----------------------
Component B trained on ``(MNDWI > 0)``, and that label is measurably wrong.
Swept against JRC Global Surface Water (occurrence > 50 %, 0.373 % of the
2024-02-18 dry-season scene):

    label                fraction    IoU    precision  recall
    MNDWI > 0  (was)      3.240 %   0.055     0.058     0.502
    MNDWI > 0.05          1.993 %   0.076     0.084     0.451
    MNDWI > 0.10 (best)   1.042 %   0.079     0.100     0.279
    NDWI  > 0             0.872 %   0.154     0.190     0.446
    OmniWaterMask         0.330 %      —         —         —

At the shipped threshold MNDWI flags **8.7x the reference area while missing
half of it**. A mask that over- and under-detects simultaneously is not a
threshold problem, so tuning is not a fix -- the best MNDWI threshold still has
precision 0.100. Sub-pixel registration was excluded as the benign explanation:
IoU only reaches 0.081 at 3 px tolerance and 79 % of the reference survives 1 px
erosion.

The three usable options are exposed here rather than hard-coded, because the
choice carries a claim and the claim must travel with the artifact.

The distillation caveat
-----------------------
``external`` normally means an OmniWaterMask raster. OWM matches the JRC extent
to within 12 %, which makes it the best available optical label -- but a U-Net
trained on it is **distilling OWM**, not learning water independently. The
resulting IoU measures copy fidelity, not accuracy, and
:func:`label_assumptions` says so in the published metrics. Anything stronger
would be a false claim.

OWM cannot be computed inside the runner: ``omniwatermask`` requires
``numpy>=2.0,<2.4`` and the runner is frozen at ``numpy==2.4.2``. So an external
label is produced in the research environment and passed in as a raster, with
its SHA-256 and grid recorded so the binding is checkable.
