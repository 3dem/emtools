# RELION optimiser; version 4.0-alpha-commit-96560b
# --o Refine3D/job029/run --auto_refine --split_random_halves --i Polish/job028/shiny.star --ref Refine3D/job025/run_half1_class001_unfil.mrc --ini_high 8 --dont_combine_weights_via_disc --scratch_dir /ssd/scheres --pool 3 --pad 2 --skip_gridding --ctf --particle_diameter 200 --flatten_solvent --zero_mask --solvent_mask MaskCreate/job020/mask.mrc --solvent_correct_fsc --oversampling 1 --healpix_order 2 --auto_local_healpix_order 4 --offset_range 5 --offset_step 2 --sym D2 --low_resol_join_halves 40 --norm --scale --j 6 --gpu 4:5:6:7 --pipeline_control Refine3D/job029/ 

# version 30001

data_optimiser_general

_rlnOutputRootName                                    Refine3D/job029/run
_rlnModelStarFile                                     Refine3D/job029/run_it016_half1_model.star
_rlnModelStarFile2                                    Refine3D/job029/run_it016_half2_model.star
_rlnExperimentalDataStarFile                          Refine3D/job029/run_it016_data.star
_rlnOrientSamplingStarFile                            Refine3D/job029/run_it016_sampling.star
_rlnCurrentIteration                                            16
_rlnNumberOfIterations                                         999
_rlnDoSplitRandomHalves                                          1
_rlnJoinHalvesUntilThisResolution                        40.000000
_rlnAdaptiveOversampleOrder                                      1
_rlnAdaptiveOversampleFraction                            0.999000
_rlnRandomSeed                                          1622621066
_rlnParticleDiameter                                    200.000000
_rlnWidthMaskEdge                                                5
_rlnDoZeroMask                                                   1
_rlnDoSolventFlattening                                          1
_rlnDoSolventFscCorrection                                       1
_rlnSolventMaskName                                   MaskCreate/job020/mask.mrc
_rlnSolventMask2Name                                  None
_rlnBodyStarFile                                      None
_rlnTauSpectrumName                                   None
_rlnMaximumCoarseImageSize                                      -1
_rlnHighresLimitExpectation                               -1.00000
_rlnLowresLimitExpectation                                -1.00000
_rlnIncrementImageSize                                          23
_rlnDoMapEstimation                                              1
_rlnDoFastSubsetOptimisation                                     0
_rlnDoExternalReconstruct                                        0
_rlnDoStochasticGradientDescent                                  0
_rlnGradEmIters                                                  0
_rlnGradHasConverged                                             0
_rlnGradCurrentStepsize                                   0.000000
_rlnGradSubsetOrder                                              0
_rlnGradSuspendFinerSamplingIter                                -1
_rlnGradSuspendLocalSamplingIter                                -1
_rlnSgdInitialIterationsFraction                          0.300000
_rlnSgdFinalIterationsFraction                            0.200000
_rlnSgdMinimumResolution                                 20.000000
_rlnSgdInitialResolution                                  -1.00000
_rlnSgdFinalResolution                                    -1.00000
_rlnSgdInitialSubsetSize                                        -1
_rlnSgdFinalSubsetSize                                          -1
_rlnSgdMuFactor                                           0.000000
_rlnSgdSkipAnneal                                                0
_rlnSgdClassInactivityThreshold                           0.000000
_rlnSgdSubsetSize                                               -1
_rlnSgdWriteEverySubset                                         10
_rlnSgdStepsize                                           -1.00000
_rlnSgdStepsizeScheme                                 ""
_rlnDoAutoRefine                                                 1
_rlnAutoLocalSearchesHealpixOrder                                4
_rlnNumberOfIterWithoutResolutionGain                            3
_rlnBestResolutionThusFar                                 0.298107
_rlnNumberOfIterWithoutChangingAssignments                       2
_rlnDoSkipAlign                                                  0
_rlnDoSkipRotate                                                 0
_rlnOverallAccuracyRotations                              0.373000
_rlnOverallAccuracyTranslationsAngst                      0.248967
_rlnChangesOptimalOrientations                            0.123072
_rlnChangesOptimalOffsets                                 0.104916
_rlnChangesOptimalClasses                                 0.000000
_rlnSmallestChangesOrientations                           0.123072
_rlnSmallestChangesOffsets                                0.093442
_rlnSmallestChangesClasses                                       0
_rlnLocalSymmetryFile                                 None
_rlnDoHelicalRefine                                              0
_rlnIgnoreHelicalSymmetry                                        0
_rlnFourierMask                                       None
_rlnHelicalTwistInitial                                   0.000000
_rlnHelicalRiseInitial                                    0.000000
_rlnHelicalCentralProportion                              0.300000
_rlnNrHelicalNStart                                              1
_rlnHelicalMaskTubeInnerDiameter                          -1.00000
_rlnHelicalMaskTubeOuterDiameter                          -1.00000
_rlnHelicalSymmetryLocalRefinement                               0
_rlnHelicalSigmaDistance                                  -1.00000
_rlnHelicalKeepTiltPriorFixed                                    0
_rlnHasConverged                                                 0
_rlnHasHighFscAtResolLimit                                       1
_rlnHasLargeSizeIncreaseIterationsAgo                            0
_rlnDoCorrectNorm                                                1
_rlnDoCorrectScale                                               1
_rlnDoCorrectCtf                                                 1
_rlnDoCenterClasses                                              0
_rlnDoIgnoreCtfUntilFirstPeak                                    0
_rlnCtfDataArePhaseFlipped                                       0
_rlnDoOnlyFlipCtfPhases                                          0
_rlnRefsAreCtfCorrected                                          1
_rlnFixSigmaNoiseEstimates                                       0
_rlnFixSigmaOffsetEstimates                                      0
_rlnMaxNumberOfPooledParticles                                  18
 
