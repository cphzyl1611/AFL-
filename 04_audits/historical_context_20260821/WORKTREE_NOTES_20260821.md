# Worktree notes

用户侧 `git worktree list`：

/home/dministrator/AFLplusplus                           c6817ce [public-release]
/home/dministrator/AFLplusplus-alfresco-cal              c6817ce [feature/alfresco-real-platform-calibration]
/home/dministrator/AFLplusplus-alfresco-gate2-hardening  fc2866d [feature/alfresco-gate2-hardening]
/home/dministrator/AFLplusplus-alfresco-levelc           5f2d721 [feature/alfresco-level-c-metadata-http]
/home/dministrator/AFLplusplus-alfresco-levelc-content   53cb267 [feature/alfresco-level-c-content-http]
/home/dministrator/AFLplusplus-p0                        2283976 [fix/p0-mab-feedback-validation]
/home/dministrator/AFLplusplus-p01                       a51ad6b [fix/p0.1-release-hardening]
/home/dministrator/AFLplusplus-v071                      c6817ce [feature/v0.7.1-real-harness-exec-seq]
/tmp/AFLplusplus-credential-hardening-remediation        c6817ce [feature/credential-hardening-remediation]

Branch containment against latest content checkpoint:
ALL listed branch heads = ancestors of 53cb267.

Known dirty worktrees:
- /home/dministrator/AFLplusplus
- /home/dministrator/AFLplusplus-alfresco-cal
- /home/dministrator/AFLplusplus-alfresco-gate2-hardening
- /home/dministrator/AFLplusplus-p0
- /tmp/AFLplusplus-credential-hardening-remediation (historical intermediate; archived separately)

Known clean worktrees:
- /home/dministrator/AFLplusplus-alfresco-levelc
- /home/dministrator/AFLplusplus-alfresco-levelc-content
- /home/dministrator/AFLplusplus-p01
- /home/dministrator/AFLplusplus-v071

Do not manually rm/reset/clean dirty worktrees as part of feature development.
The temporary credential-hardening worktree was independently archived by the user; it is not needed for the next feature stage.
