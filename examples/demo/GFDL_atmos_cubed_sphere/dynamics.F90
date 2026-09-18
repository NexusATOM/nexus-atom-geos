! Synthetic teaching example, NOT an upstream FV3 routine or scientific oracle.
module demo_dynamics
  use iso_fortran_env, only: real64
  implicit none
contains
  subroutine pressure_log(n, pressure, log_pressure)
    integer, intent(in) :: n
    real(real64), intent(in) :: pressure(n)
    real(real64), intent(out) :: log_pressure(n)
    integer :: i
    ! Caller must supply positive pressures in a consistent unit convention.
    ! A CUDA port would need an explicit array layout and transfer policy.
    do i = 1, n
      log_pressure(i) = log(pressure(i))
    end do
  end subroutine pressure_log
end module demo_dynamics
